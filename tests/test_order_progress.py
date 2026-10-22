import unittest
from crud.order_progress import calculate_progress


class OrderProgressTests(unittest.TestCase):
    def progress(self, status="active", shipped=None, allocated=None, contracts=None, required=None):
        return calculate_progress(status, required or {("A", False): 2}, shipped or [], allocated or [],
                                  contracts or [], lambda row: (row["机型"], row.get("high", False)))["order_status_label"]

    def machine(self, sn, model="A", **extra):
        return {"流水号": sn, "机型": model, **extra}

    def test_planning_stages(self):
        self.assertEqual(self.progress(), "待规划")
        self.assertEqual(self.progress(contracts=[{"状态": "已规划"}]), "已规划")
        self.assertEqual(self.progress(contracts=[{"状态": "已规划"}, {"状态": "待规划"}]), "待规划")

    def test_transferred_contract_needs_complete_plan(self):
        row = {"状态": "已转订单", "排产数量": "2", "指定批次/来源": {"batch": 1}}
        self.assertEqual(self.progress(contracts=[row]), "待规划")
        row["指定批次/来源"] = {"batch": 2}
        self.assertEqual(self.progress(contracts=[row]), "已规划")

    def test_counts_and_machine_details_deduplicate_shipping(self):
        result = calculate_progress("ready", {("A", False): 3},
            [self.machine("1"), self.machine("1")],
            [self.machine("1"), self.machine("2"), self.machine("2")], [],
            lambda row: (row["机型"], False), include_machines=True)
        self.assertEqual(result["required_count"], 3)
        self.assertEqual(result["shipped_count"], 1)
        self.assertEqual(result["allocated_count"], 1)
        self.assertEqual(len(result["machines"]), 2)
        self.assertEqual(result["order_status_label"], "待配齐")

    def test_partial_shipment_and_confirmation(self):
        shipped = [self.machine("1")]
        allocated = [self.machine("2")]
        self.assertEqual(self.progress(shipped=shipped), "待配齐")
        self.assertEqual(self.progress(shipped=shipped, allocated=allocated), "待配齐")
        self.assertEqual(self.progress("ready", shipped, allocated), "待发货")
        self.assertEqual(self.progress("ready", shipped, [self.machine("2", "B")]), "待配齐")

    def test_completion_dedup_and_return(self):
        self.assertEqual(self.progress(shipped=[self.machine("1"), self.machine("2")]), "已完成")
        self.assertEqual(self.progress("done", shipped=[self.machine("1"), self.machine("1")]), "待配齐")
        self.assertEqual(self.progress("done", shipped=[self.machine("1")]), "待配齐")

    def test_variant_and_special_states(self):
        self.assertEqual(self.progress("ready", allocated=[self.machine("1"), self.machine("2", high=True)]), "待配齐")
        for status, label in [("deleted", "已删除"), ("canceled", "已取消"), ("pending_review", "待二次确认")]:
            self.assertEqual(self.progress(status, [self.machine("1"), self.machine("2")]), label)


if __name__ == "__main__":
    unittest.main()
