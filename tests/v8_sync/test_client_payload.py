import json
import unittest

from v8_sync.client import _json_bytes, _machine_bridge_payload


class MachineBridgePayloadTests(unittest.TestCase):
    def test_machine_endpoint_only_serializes_machine_identity_fields(self):
        payload = {
            "snapshotId": "snap-1",
            "payloadSha256": "internal-digest",
            "sourceWatermark": {"machines": "2026-10-22"},
            "tables": {
                "machines": [{
                    "machine_no": "96-05-11",
                    "model": "FR-500",
                    "customer": "dealer",
                    "shipping_date": "2026-10-01",
                    "status": "库存中",
                    "source_updated_at": "2026-10-22T00:00:00Z",
                    "warranty_start": "2026-10-01",
                    "agent": "private-agent",
                }],
                "materials": [{"material_code": "private-material"}],
                "materialInstances": [{"serial_no": "private-component"}],
                "machineMaterialBindings": [{"position_code": "private-position"}],
                "photoItems": [{"item_name": "private-photo-config"}],
            },
        }

        encoded = _json_bytes(_machine_bridge_payload(payload))
        result = json.loads(encoded)

        self.assertEqual(set(result), {"snapshotId", "tables"})
        self.assertEqual(set(result["tables"]), {"machines"})
        self.assertEqual(result["tables"]["machines"][0], {
            "machine_no": "96-05-11",
            "model": "FR-500",
            "customer": "dealer",
            "shipping_date": "2026-10-01",
            "status": "库存中",
            "source_updated_at": "2026-10-22T00:00:00Z",
        })
        self.assertNotIn(b"private-", encoded)


if __name__ == "__main__":
    unittest.main()
