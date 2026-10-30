import pytest

from api.routes.inventory import revert_shipping
from api.routes.model_dictionary import delete_model_name
from api.routes.planning import hard_delete_sales_order_api, release_order_inventory_api, update_contract_status, update_sales_order_api


def test_legacy_shipping_revert_is_blocked():
    with pytest.raises(Exception) as exc:
        revert_shipping(None, None, 'tester', {'username': 'tester'})
    assert getattr(exc.value, 'status_code', None) == 409


def test_legacy_order_delete_is_blocked():
    with pytest.raises(Exception) as exc:
        hard_delete_sales_order_api('SO-1', 'tester', {'username': 'tester'})
    assert getattr(exc.value, 'status_code', None) == 409


def test_legacy_order_release_is_blocked():
    with pytest.raises(Exception) as exc:
        release_order_inventory_api('SO-1', None, None, 'tester', {'username': 'tester'})
    assert getattr(exc.value, 'status_code', None) == 409


def test_legacy_model_delete_is_blocked():
    with pytest.raises(Exception) as exc:
        delete_model_name(None, None, {})
    assert getattr(exc.value, 'status_code', None) == 409
