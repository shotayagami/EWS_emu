"""Load the private ARIB catalog when present, otherwise use fictional examples."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from area_codes import AREAS

LOCAL_CATALOG_PATH = Path(__file__).with_name("digital_service_catalog.local.py")

if LOCAL_CATALOG_PATH.is_file():
    spec = spec_from_file_location("digital_service_catalog_local", LOCAL_CATALOG_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"ローカルサービスカタログを読み込めません: {LOCAL_CATALOG_PATH}")
    local_catalog = module_from_spec(spec)
    spec.loader.exec_module(local_catalog)

    CATALOG_IS_LOCAL = True
    AREA_GROUPS = local_catalog.AREA_REGION_IDS
    # TR-B14 assigns an eight-ID TV range per region broadcaster; select its first service ID.
    SERVICES = tuple(
        (region_id, 0x0400 * region_id + 8 * broadcaster_id, name_en, name_ja)
        for region_id, broadcaster_id, name_en, name_ja in local_catalog.DTV_SERVICES
    )
else:
    CATALOG_IS_LOCAL = False
    AREA_GROUPS = {name: [group] for group, (name, _code) in enumerate(AREAS, 1)}
    AREA_GROUPS["地域共通"] = None
    SERVICES = tuple(
        (group, 0xF000 + (group - 1) * 2 + slot, "", f"ダミー局{group:02d}-{slot + 1}")
        for group in range(1, len(AREAS) + 1)
        for slot in range(2)
    )
