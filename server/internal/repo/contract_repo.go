package repo

import (
	"fmt"
	"strings"
	"time"

	"gorm.io/gorm"

	"smart-scheduling/server/internal/model"
	"smart-scheduling/server/internal/modeltype"
)

type ContractRepo struct {
	db *gorm.DB
}

func NewContractRepo(db *gorm.DB) *ContractRepo { return &ContractRepo{db: db} }

type contractRow struct {
	ContractNo  string    `gorm:"column:contract_no"`
	Customer    string    `gorm:"column:customer"`
	DealerName  string    `gorm:"column:dealer_name"`
	ModelName   string    `gorm:"column:model_name"`
	ModelFamily string    `gorm:"column:model_family"`
	Quantity    int       `gorm:"column:quantity"`
	DueDate     time.Time `gorm:"column:due_date"`
	SalesID     string    `gorm:"column:sales_id"`
	Remark      string    `gorm:"column:remark"`
}

func (r *ContractRepo) ReadValidContractUnits() ([]model.ContractUnit, error) {
	colSet, err := r.loadFactoryPlanColumns()
	if err != nil {
		return nil, err
	}

	contractCol, ok := pickExistingColumn(colSet, "\u5408\u540c\u53f7", "contract_no", "contract_number")
	if !ok {
		return nil, fmt.Errorf("factory_plan missing contract number column")
	}
	modelCol, ok := pickExistingColumn(colSet, "\u673a\u578b", "model_name", "model")
	if !ok {
		return nil, fmt.Errorf("factory_plan missing model column")
	}
	dueCol, ok := pickExistingColumn(colSet, "\u8981\u6c42\u4ea4\u671f", "\u4ea4\u671f", "due_date")
	if !ok {
		return nil, fmt.Errorf("factory_plan missing due date column")
	}

	customerCol, _ := pickExistingColumn(colSet, "\u5ba2\u6237\u540d", "\u5ba2\u6237", "customer", "customer_name")
	dealerCol, _ := pickExistingColumn(colSet, "\u4ee3\u7406\u5546", "\u7ecf\u9500\u5546", "\u6e20\u9053\u5546", "dealer_name", "dealer", "agent_name", "distributor_name")
	qtyCol, _ := pickExistingColumn(colSet, "\u6392\u4ea7\u6570\u91cf", "\u6570\u91cf", "qty", "quantity")
	statusCol, hasStatus := pickExistingColumn(colSet, "\u72b6\u6001", "status")
	salesCol, hasSales := pickExistingColumn(colSet, "\u4e1a\u52a1\u5458", "\u9500\u552e\u5458", "sales", "sales_id")
	remarkCol, hasRemark := pickExistingColumn(colSet, "\u5907\u6ce8", "remark")

	customerExpr := "''"
	if customerCol != "" {
		customerExpr = fmt.Sprintf("COALESCE(fp.%s, '')", quoteIdentifier(customerCol))
	}
	dealerExpr := "''"
	if dealerCol != "" {
		dealerExpr = fmt.Sprintf("COALESCE(fp.%s, '')", quoteIdentifier(dealerCol))
	}
	quantityExpr := "1"
	if qtyCol != "" {
		quantityExpr = fmt.Sprintf("CAST(COALESCE(NULLIF(fp.%s, ''), 1) AS UNSIGNED)", quoteIdentifier(qtyCol))
	}
	salesExpr := "''"
	if hasSales {
		salesExpr = fmt.Sprintf("COALESCE(fp.%s, '')", quoteIdentifier(salesCol))
	}
	remarkExpr := "''"
	if hasRemark {
		remarkExpr = fmt.Sprintf("COALESCE(fp.%s, '')", quoteIdentifier(remarkCol))
	}

	statusFilter := ""
	if hasStatus {
		statusFilter = fmt.Sprintf(
			"AND TRIM(COALESCE(fp.%s, '')) = %s",
			quoteIdentifier(statusCol),
			quoteSQLString("\u5f85\u89c4\u5212"),
		)
	}

	sql := fmt.Sprintf(`
SELECT
  fp.%s AS contract_no,
  %s AS customer,
  %s AS dealer_name,
  fp.%s AS model_name,
  md.model_family AS model_family,
  %s AS quantity,
  CAST(fp.%s AS DATE) AS due_date,
  %s AS sales_id,
  %s AS remark
FROM factory_plan fp
INNER JOIN model_dictionary md
  ON fp.%s COLLATE utf8mb4_general_ci = md.model_name COLLATE utf8mb4_general_ci
WHERE md.enabled = 1
  %s
  AND fp.%s IS NOT NULL
  AND fp.%s != ''
  AND CAST(fp.%s AS DATE) >= CURDATE()
ORDER BY due_date ASC, contract_no ASC`,
		quoteIdentifier(contractCol),
		customerExpr,
		dealerExpr,
		quoteIdentifier(modelCol),
		quantityExpr,
		quoteIdentifier(dueCol),
		salesExpr,
		remarkExpr,
		quoteIdentifier(modelCol),
		statusFilter,
		quoteIdentifier(dueCol),
		quoteIdentifier(dueCol),
		quoteIdentifier(dueCol),
	)

	var rows []contractRow
	if err := r.db.Raw(sql).Scan(&rows).Error; err != nil {
		return nil, err
	}

	units := make([]model.ContractUnit, 0)
	for _, row := range rows {
		modelType := row.ModelFamily
		if modelType == "" {
			modelType = modeltype.Normalize(row.ModelName)
		}
		qty := row.Quantity
		if qty <= 0 {
			qty = 1
		}
		for i := 0; i < qty; i++ {
			units = append(units, model.ContractUnit{
				ContractNo: row.ContractNo,
				Customer:   row.Customer,
				DealerName: row.DealerName,
				ModelName:  row.ModelName,
				ModelType:  modelType,
				DueDate:    row.DueDate,
				SalesID:    row.SalesID,
				Remark:     row.Remark,
			})
		}
	}
	return units, nil
}

func (r *ContractRepo) loadFactoryPlanColumns() (map[string]bool, error) {
	var rows []struct {
		ColumnName string `gorm:"column:COLUMN_NAME"`
	}
	err := r.db.Raw(`
SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'factory_plan'`).Scan(&rows).Error
	if err != nil {
		return nil, err
	}

	set := make(map[string]bool, len(rows))
	for _, row := range rows {
		set[row.ColumnName] = true
	}
	return set, nil
}

func pickExistingColumn(set map[string]bool, candidates ...string) (string, bool) {
	for _, name := range candidates {
		if set[name] {
			return name, true
		}
	}
	return "", false
}

func quoteIdentifier(name string) string {
	return "`" + strings.ReplaceAll(name, "`", "``") + "`"
}

func quoteSQLString(value string) string {
	return "'" + strings.ReplaceAll(value, "'", "''") + "'"
}
