import unittest
from vci_volume_basis import declaration, validate_forward

class VCIVolumeBasisTests(unittest.TestCase):
    def test_declaration_is_fail_closed(self):
        item = declaration()
        self.assertEqual(item["volume_basis"], "unknown")
        self.assertFalse(item["volume_basis_verified"])
        self.assertEqual(item["raw_payload_fields"]["primary"], "v")
    def test_forward_gate_rejects_unqualified_record(self):
        with self.assertRaises(ValueError):
            validate_forward({"provider":"VCI"})
        with self.assertRaises(ValueError):
            validate_forward({"provider":"VCI", "raw_volume_field":"v", "raw_volume_alias_field":"accumulatedVolume", "volume_basis":"unknown", "volume_basis_verified":False, "basis_evidence_id":"x"})

if __name__ == "__main__": unittest.main()