"""Session research presets; the API remains authoritative for research inputs."""
from __future__ import annotations

from copy import deepcopy
import json
import math
import re
from typing import Any, Callable

import streamlit as st


SCHEMA_VERSION = 1
MAX_PRESET_BYTES = 64 * 1024
MAX_PRESETS = 20
MAX_NAME_LENGTH = 80
_RESPONSE_FIELDS = {
    "pair", "expiry_a", "expiry_b", "start", "end", "cutoff", "window",
    "z_threshold", "capital", "max_lots", "min_volume", "min_oi",
    "holding_days", "execution_delay", "exit_delay", "cost_bps",
    "slippage_bps", "seed", "simulations", "volatility_stress", "mode",
    "baseline", "cost_schedule",
}


class PresetError(ValueError):
    """An invalid portable preset or an unsafe attempt to replace one."""


def _check_json_values(value: Any) -> None:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise PresetError("Preset JSON object keys must be strings.")
        for item in value.values():
            _check_json_values(item)
    elif isinstance(value, list):
        for item in value:
            _check_json_values(item)
    elif type(value) is float:
        if not math.isfinite(value):
            raise PresetError("Preset settings must contain only finite JSON values.")
    elif value is not None and type(value) not in (str, int, bool):
        raise PresetError("Preset settings must contain only JSON values.")


def validate_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip():
        raise PresetError("Give this preset a name.")
    name = name.strip()
    if len(name) > MAX_NAME_LENGTH or any(ord(char) < 32 for char in name):
        raise PresetError("Preset names must be at most 80 characters and contain no control characters.")
    return name


def _check_envelope(payload: Any) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "name", "config"}:
        raise PresetError("Use a research preset JSON file with schema_version, name and config.")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
        raise PresetError("This preset version is unsupported. Expected schema_version 1.")
    name = validate_name(payload["name"])
    if not isinstance(payload["config"], dict):
        raise PresetError("Preset config must be a JSON object.")
    if {"api_url", "request_timeout", "preferences"}.intersection(payload["config"]):
        raise PresetError("Research presets cannot contain API connection settings.")
    try:
        _check_json_values(payload["config"])
    except RecursionError as exc:
        raise PresetError("The preset JSON is nested too deeply.") from exc
    return {"schema_version": SCHEMA_VERSION, "name": name, "config": payload["config"]}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PresetError(f"The JSON file repeats the field {key!r}.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PresetError(f"Non-finite JSON numbers ({value}) are not supported.")


def parse_preset(data: bytes | str) -> dict:
    """Validate the portable format only; research rules are checked by the API."""
    if not isinstance(data, (bytes, str)):
        raise PresetError("Choose a UTF-8 JSON preset file.")
    try:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        if len(raw) > MAX_PRESET_BYTES:
            raise PresetError("Preset files must be 64 KiB or smaller.")
        payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant)
    except PresetError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PresetError("The preset file is not valid UTF-8 JSON.") from exc
    return _check_envelope(payload)


def serialize_preset(preset: dict) -> str:
    """Export every research field without credentials, coercion or NaN values."""
    checked = _check_envelope(preset)
    try:
        output = json.dumps(checked, indent=2, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise PresetError("Preset settings must contain only finite JSON values.") from exc
    # Apply the same byte limit to exports, so every download can be imported.
    parse_preset(output)
    return output


def make_preset(name: str, config: dict) -> dict:
    return parse_preset(serialize_preset({"schema_version": SCHEMA_VERSION,
                                         "name": name, "config": config}))


def _retains_fields(original: Any, validated: Any) -> bool:
    """Accept added defaults, but never silently discard or alter supplied values."""
    if isinstance(original, dict):
        return isinstance(validated, dict) and all(
            key in validated and _retains_fields(value, validated[key])
            for key, value in original.items()
        )
    if isinstance(original, list):
        return isinstance(validated, list) and len(original) == len(validated) and all(
            _retains_fields(left, right) for left, right in zip(original, validated)
        )
    if isinstance(original, bool) or isinstance(validated, bool):
        return type(original) is type(validated) and original == validated
    return original == validated


def validate_with_api(preset: dict, api: Callable[..., Any]) -> dict:
    """Validate through the backend and reject incomplete or lossy API replies."""
    checked = parse_preset(serialize_preset(preset))
    result = api("POST", "/api/validate-config", body=deepcopy(checked["config"]))
    if not isinstance(result, dict) or not _RESPONSE_FIELDS.issubset(result):
        raise PresetError("The API returned an incomplete research configuration. The preset was not applied.")
    integers = ("window", "max_lots", "min_volume", "min_oi", "holding_days", "execution_delay", "exit_delay", "seed", "simulations")
    numbers = ("z_threshold", "capital", "cost_bps", "slippage_bps", "volatility_stress")
    if (not isinstance(result["pair"], list) or len(result["pair"]) != 2
            or any(not isinstance(value, str) for value in result["pair"])
            or result["mode"] not in ("real", "synthetic") or result["baseline"] not in ("A", "B", "C")
            or any(type(result[key]) is not int for key in integers)
            or any(type(result[key]) not in (int, float) for key in numbers)
            or any(result[key] is not None and not isinstance(result[key], str)
                   for key in ("expiry_a", "expiry_b", "start", "end", "cutoff"))
            or not isinstance(result["cost_schedule"], list)
            or any(not isinstance(item, dict) for item in result["cost_schedule"])):
        raise PresetError("The API returned an invalid research configuration. The preset was not applied.")
    if not _retains_fields(checked["config"], result):
        raise PresetError("The API changed or dropped supplied settings. The preset was not applied.")
    return make_preset(checked["name"], result)


def save_preset(saved: dict, preset: dict, *, replace: bool = False) -> dict:
    """Return an independent session collection without implicit replacement."""
    checked = parse_preset(serialize_preset(preset))
    name = checked["name"]
    if name in saved and not replace:
        raise PresetError("A preset with this name already exists. Select Replace existing preset to overwrite it.")
    if name not in saved and len(saved) >= MAX_PRESETS:
        raise PresetError("You can save 20 presets per session. Delete a saved preset before adding another.")
    return {**deepcopy(saved), name: checked}


def _queue_load(preset: dict) -> None:
    st.session_state["pending_research_preset"] = deepcopy(preset)
    st.rerun()


def render_presets(config: dict, api: Callable[..., Any]) -> None:
    """Render anywhere after controls; the caller applies pending config next run.

    ``pending_research_preset`` is the full version-1 envelope, not just config.
    Saved presets last for this Streamlit session. Load does not call the API.
    """
    saved = st.session_state.setdefault("research_presets", {})
    with st.expander("Research presets"):
        st.caption("Save research settings for this session, or download a JSON copy to reuse later. Saving and importing validate settings with the research API.")
        notice = st.session_state.pop("research_preset_notice", None)
        if notice:
            st.success(notice)
        name = st.text_input("Preset name", max_chars=MAX_NAME_LENGTH, key="research_preset_name")
        replace = st.checkbox("Replace existing preset", key="research_preset_replace")
        if st.button("Save current settings", key="research_preset_save"):
            try:
                candidate = make_preset(name, config)
                # Check duplicate and capacity before making a network request.
                save_preset(saved, candidate, replace=replace)
                validated = validate_with_api(candidate, api)
                st.session_state["research_presets"] = save_preset(saved, validated, replace=replace)
                st.session_state["research_preset_notice"] = f"Saved {validated['name']}. Download it to keep a copy after this session."
                st.rerun()
            except (PresetError, RuntimeError) as exc:
                st.error(str(exc))

        selected = st.selectbox("Saved preset", [None, *sorted(saved)],
                                format_func=lambda value: "Current research settings" if value is None else value,
                                key="research_preset_selected")
        load, delete = st.columns(2)
        if load.button("Load preset", disabled=selected is None, key="research_preset_load"):
            _queue_load(saved[selected])
        if delete.button("Delete saved preset", disabled=selected is None, key="research_preset_delete"):
            st.session_state["research_presets"] = {key: value for key, value in saved.items() if key != selected}
            st.session_state["research_preset_notice"] = f"Deleted {selected}."
            st.rerun()
        st.caption(f"{len(saved)} of {MAX_PRESETS} session presets saved.")
        try:
            download = saved[selected] if selected is not None else make_preset(name or "Current research", config)
            filename = re.sub(r"[^A-Za-z0-9_-]+", "-", download["name"]).strip("-") or "research"
            st.download_button("Download preset JSON", serialize_preset(download),
                               file_name=f"aurum-x-{filename}.json", mime="application/json",
                               key="research_preset_download")
        except PresetError as exc:
            st.warning(str(exc))

        upload = st.file_uploader("Import research preset", type=["json"], key="research_preset_upload",
                                  help="A version-1 Aurum research preset, at most 64 KiB. Importing applies its settings; save it above to add it to this session.")
        if st.button("Validate and load JSON", disabled=upload is None, key="research_preset_import"):
            try:
                if upload.size > MAX_PRESET_BYTES:
                    raise PresetError("Preset files must be 64 KiB or smaller.")
                candidate = parse_preset(upload.getvalue())
                validated = validate_with_api(candidate, api)
                _queue_load(validated)
            except (PresetError, RuntimeError) as exc:
                st.error(str(exc))
