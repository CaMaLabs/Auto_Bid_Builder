from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any


SERVICE_NAME = "AutoBidBuilder"
DEFAULT_HOME = Path(os.getenv("AUTO_BID_BUILDER_HOME", Path.home() / ".auto_bid_builder"))


@dataclass
class ProviderSettings:
    id: str
    label: str
    kind: str
    enabled: bool = False
    feed_url: str = ""
    base_url: str = ""
    username: str = ""
    notes: str = ""
    credential_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["credential_fields"] = list(self.credential_fields)
        return data


@dataclass
class AppSettings:
    preferred_states: list[str] = field(default_factory=lambda: ["CA", "NV"])
    lookback_days: int = 30
    minimum_score: float = 20.0
    providers: list[ProviderSettings] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_states": self.preferred_states,
            "lookback_days": self.lookback_days,
            "minimum_score": self.minimum_score,
            "providers": [x.to_dict() for x in self.providers],
        }


DEFAULT_PROVIDERS = (
    ProviderSettings(
        id="cca_public",
        label="California Construction Authority - public opportunities",
        kind="cca_public",
        enabled=True,
        base_url="https://ccauthority.org/bid-opportunites/",
        notes="Anonymous public page. Some linked bid packets may require free Public Purchase registration.",
    ),
    ProviderSettings(
        id="ca_dgs_resd",
        label="California DGS RESD - construction solicitations",
        kind="ca_dgs_resd",
        enabled=True,
        base_url="https://www.dgs.ca.gov/RESD/Resources/Page-Content/Real-Estate-Services-Division-Resources-List-Folder/Current-Real-Estate-Services-Division-Solicitations",
        notes="Anonymous public solicitation list. If DGS blocks automated requests, sync records the error without stopping other sources.",
    ),
    ProviderSettings(
        id="sam",
        label="SAM.gov Contract Opportunities",
        kind="sam",
        credential_fields=("api_key",),
        notes="Official API. Requires a SAM.gov public API key.",
    ),
    ProviderSettings(
        id="buildingconnected",
        label="Autodesk BuildingConnected / Bid Board Pro",
        kind="buildingconnected",
        credential_fields=("client_id", "client_secret", "refresh_token"),
        notes="OAuth/API integration placeholder until JTI confirms access and Autodesk app credentials.",
    ),
    ProviderSettings(
        id="dodge",
        label="Dodge Construction Network",
        kind="dodge",
        credential_fields=("client_id", "client_secret", "api_key"),
        notes="Commercial API integration placeholder.",
    ),
    ProviderSettings(
        id="planhub",
        label="PlanHub",
        kind="planhub",
        credential_fields=("api_key", "username", "password"),
        notes="Commercial API/account integration placeholder.",
    ),
    ProviderSettings(
        id="constructconnect",
        label="ConstructConnect",
        kind="constructconnect",
        credential_fields=("api_key", "client_id", "client_secret"),
        notes="External API integration placeholder.",
    ),
    ProviderSettings(
        id="smartbid",
        label="SmartBid",
        kind="smartbid",
        credential_fields=("api_key", "username", "password"),
        notes="Authenticated integration placeholder.",
    ),
    ProviderSettings(
        id="custom_feed",
        label="Custom RSS / Atom feed",
        kind="rss",
        feed_url="",
        notes="Use for any public bid board that exposes RSS or Atom.",
    ),
)


def settings_path(home: Path | None = None) -> Path:
    root = home or DEFAULT_HOME
    return root / "settings.json"


def cache_path(home: Path | None = None) -> Path:
    root = home or DEFAULT_HOME
    return root / "opportunities.json"


def _merge_provider(raw: dict[str, Any], default: ProviderSettings | None = None) -> ProviderSettings:
    base = default.to_dict() if default else {}
    base.update(raw)
    base["credential_fields"] = tuple(base.get("credential_fields") or ())
    return ProviderSettings(**base)


def load_settings(home: Path | None = None) -> AppSettings:
    path = settings_path(home)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}

    defaults = {x.id: x for x in DEFAULT_PROVIDERS}
    configured = {str(x.get("id")): x for x in raw.get("providers", []) if x.get("id")}
    providers: list[ProviderSettings] = []
    for provider_id, default in defaults.items():
        providers.append(_merge_provider(configured.pop(provider_id, {}), default))
    for provider_id, item in configured.items():
        providers.append(_merge_provider(item, ProviderSettings(provider_id, provider_id, item.get("kind", "rss"))))

    return AppSettings(
        preferred_states=[str(x).upper() for x in raw.get("preferred_states", ["CA", "NV"]) if str(x).strip()],
        lookback_days=max(1, int(raw.get("lookback_days", 30))),
        minimum_score=float(raw.get("minimum_score", 20.0)),
        providers=providers,
    )


def save_settings(settings: AppSettings, home: Path | None = None) -> Path:
    path = settings_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


class SecretStore:
    """Store provider credentials outside the repository.

    Environment variables are always supported as read-only overrides. When the
    optional ``keyring`` package has a usable OS backend, values saved from the
    settings page go to the operating-system credential store.
    """

    def _name(self, provider_id: str, field_name: str) -> str:
        return f"{provider_id}:{field_name}"

    def _env_name(self, provider_id: str, field_name: str) -> str:
        return f"ABB_{provider_id}_{field_name}".upper().replace("-", "_")

    def get(self, provider_id: str, field_name: str) -> str | None:
        env = os.getenv(self._env_name(provider_id, field_name))
        if env:
            return env
        try:
            import keyring

            return keyring.get_password(SERVICE_NAME, self._name(provider_id, field_name))
        except Exception:
            return None

    def set(self, provider_id: str, field_name: str, value: str) -> None:
        try:
            import keyring

            if value:
                keyring.set_password(SERVICE_NAME, self._name(provider_id, field_name), value)
            else:
                try:
                    keyring.delete_password(SERVICE_NAME, self._name(provider_id, field_name))
                except Exception:
                    pass
        except Exception as exc:
            raise RuntimeError(
                "No usable OS credential-store backend is available. Set the corresponding ABB_* environment variable instead."
            ) from exc

    def has(self, provider_id: str, field_name: str) -> bool:
        return bool(self.get(provider_id, field_name))
