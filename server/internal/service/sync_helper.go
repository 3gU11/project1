package service

import (
	"fmt"
	"log"
	"strings"

	"gorm.io/gorm"
	"smart-scheduling/server/internal/model"
)

// SyncFinishedGoodsByUnitIDs ensures that machine info in finished_goods_data is up-to-date with the sandbox card.
func SyncFinishedGoodsByUnitIDs(tx *gorm.DB, unitIDs []string) error {
	if len(unitIDs) == 0 {
		return nil
	}
	cols, err := tableColumns(tx, "finished_goods_data")
	if err != nil {
		return err
	}
	if !cols["流水号"] {
		return fmt.Errorf("finished_goods_data missing column: 流水号")
	}

	var units []model.Unit
	if err := tx.Table("units").
		Select(`
			units.*,
			fg.状态 AS fg_status,
			fg.合同备注 AS fg_remark,
			fg.客户 AS fg_customer,
			fg.代理商 AS fg_dealer,
			fg.合同号 AS fg_contract_no,
			fg.占用订单号 AS fg_sales_id
		`).
		Joins("LEFT JOIN finished_goods_data fg ON fg.流水号 = COALESCE(units.serial_no, units.forecast_serial_no) COLLATE utf8mb4_general_ci").
		Where("units.unit_id IN ?", unitIDs).
		Find(&units).Error; err != nil {
		return err
	}
	for _, u := range units {
		contractNo := strings.TrimSpace(strPtrVal(u.ContractNo))
		salesID := strings.TrimSpace(strPtrVal(u.SalesID))
		customer := strings.TrimSpace(strPtrVal(u.Customer))
		dealerName := strings.TrimSpace(strPtrVal(u.DealerName))
		orderRemark := strings.TrimSpace(strPtrVal(u.OrderRemark))
		fgStatus := strings.TrimSpace(strPtrVal(u.FgStatus))
		if shouldSkipFinishedGoodsSync(fgStatus) {
			log.Printf("[Sync] Skipping finished_goods_data sync for unit %s because status %q is protected", u.UnitID, fgStatus)
			continue
		}

		updates := map[string]interface{}{}
		if cols["合同号"] {
			updates["合同号"] = contractNo
		}
		if cols["占用订单号"] {
			updates["占用订单号"] = salesID
		}
		if cols["客户"] {
			updates["客户"] = customer
		}
		if cols["代理商"] {
			updates["代理商"] = dealerName
		}
		if cols["合同备注"] {
			updates["合同备注"] = orderRemark
		}
		if cols["状态"] {
			if contractNo != "" {
				updates["状态"] = "已绑定"
			} else if fgStatus == "已绑定" {
				updates["状态"] = "待入库"
			}
		}
		if len(updates) == 0 {
			continue
		}
		serials := unitSerialCandidates(u)
		if len(serials) == 0 {
			continue
		}
		log.Printf("[Sync] Syncing unit %s (SNs: %v) to finished_goods_data with updates: %v", u.UnitID, serials, updates)

		result := tx.Table("finished_goods_data").
			Where("TRIM(`流水号`) IN ?", serials).
			Updates(updates)

		if result.Error != nil {
			log.Printf("[Sync] Error updating finished_goods_data for unit %s: %v", u.UnitID, result.Error)
			return result.Error
		}
		log.Printf("[Sync] Finished goods sync for unit %s: %d rows affected", u.UnitID, result.RowsAffected)
	}
	return nil
}

func shouldSkipFinishedGoodsSync(status string) bool {
	status = strings.TrimSpace(status)
	return status == "待发货" ||
		status == "已出库" ||
		status == "已发货" ||
		status == "报废" ||
		strings.HasPrefix(status, "库存中")
}

// SyncPlanImportByUnitIDs keeps the import staging row aligned with edits made on kanban cards.
func SyncPlanImportByUnitIDs(tx *gorm.DB, unitIDs []string, fields map[string]interface{}) error {
	if len(unitIDs) == 0 || len(fields) == 0 {
		return nil
	}
	cols, err := tableColumns(tx, "plan_import")
	if err != nil {
		return err
	}
	if !cols["流水号"] {
		return fmt.Errorf("plan_import missing column: 流水号")
	}

	updates := map[string]interface{}{}
	if value, ok := fields["model_type"]; ok && cols["机型"] {
		updates["机型"] = stringField(value)
	}
	if value, ok := fields["customer"]; ok && cols["客户"] {
		updates["客户"] = stringField(value)
	}
	if value, ok := fields["dealer_name"]; ok && cols["代理商"] {
		updates["代理商"] = stringField(value)
	}
	if value, ok := fields["order_remark"]; ok && cols["合同备注"] {
		updates["合同备注"] = stringField(value)
	}
	if len(updates) == 0 {
		return nil
	}

	var units []model.Unit
	if err := tx.Table("units").
		Where("unit_id IN ?", unitIDs).
		Find(&units).Error; err != nil {
		return err
	}

	for _, u := range units {
		serials := unitSerialCandidates(u)
		if len(serials) == 0 {
			continue
		}
		log.Printf("[Sync] Syncing unit %s (SNs: %v) to plan_import with updates: %v", u.UnitID, serials, updates)

		result := tx.Table("plan_import").
			Where("TRIM(`流水号`) IN ?", serials).
			Updates(updates)

		if result.Error != nil {
			log.Printf("[Sync] Error updating plan_import for unit %s: %v", u.UnitID, result.Error)
			return result.Error
		}
		log.Printf("[Sync] Plan import sync for unit %s: %d rows affected", u.UnitID, result.RowsAffected)
	}
	return nil
}

func unitSerialCandidates(u model.Unit) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0, 3)
	for _, v := range []string{strPtrVal(u.SerialNo), strPtrVal(u.ForecastSerialNo), u.UnitID} {
		s := strings.TrimSpace(v)
		if s == "" {
			continue
		}
		if _, ok := seen[s]; ok {
			continue
		}
		seen[s] = struct{}{}
		result = append(result, s)
	}
	return result
}

func tableColumns(tx *gorm.DB, tableName string) (map[string]bool, error) {
	var rows []struct {
		Field string `gorm:"column:Field"`
	}
	if err := tx.Raw("SHOW COLUMNS FROM " + tableName).Scan(&rows).Error; err != nil {
		return nil, err
	}
	cols := make(map[string]bool, len(rows))
	for _, r := range rows {
		cols[r.Field] = true
	}
	return cols, nil
}

func strPtrVal(v *string) string {
	if v == nil {
		return ""
	}
	return *v
}

func stringField(v interface{}) string {
	if v == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(v))
}
