package model

import (
	"time"

	"gorm.io/datatypes"
)

const (
	StatusPredicted    = "Predicted"
	StatusConfirmed    = "Confirmed"
	StatusInProduction = "In_Production"
	StatusCompleted    = "Completed"

	LineIdle = "Idle"
	LineBusy = "Busy"

	QueueWaiting = "Waiting"
	QueuePulled  = "Pulled"
)

type Batch struct {
	BatchID             string         `gorm:"column:batch_id;primaryKey" json:"batch_id"`
	BatchNo             int            `gorm:"column:batch_no" json:"batch_no"`
	BatchCode           *string        `gorm:"column:batch_code" json:"batch_code"`
	ForecastSlotNo      *int           `gorm:"->;column:forecast_slot_no" json:"forecast_slot_no,omitempty"`
	ModelType           string         `gorm:"column:model_type" json:"model_type"`
	Capacity            int            `gorm:"column:capacity" json:"capacity"`
	Status              string         `gorm:"column:status" json:"status"`
	DueDateStart        *time.Time     `gorm:"column:due_date_start" json:"due_date_start"`
	DueDateEnd          *time.Time     `gorm:"column:due_date_end" json:"due_date_end"`
	ExpectedInboundDate *time.Time     `gorm:"column:expected_inbound_date" json:"expected_inbound_date"`
	CapacitySnapshot    datatypes.JSON `gorm:"column:capacity_snapshot" json:"capacity_snapshot"`
	Source              string         `gorm:"column:source" json:"source"`
	ProductionLineID    *string        `gorm:"column:production_line_id" json:"production_line_id"`
	Units               []Unit         `gorm:"foreignKey:BatchID;references:BatchID" json:"units,omitempty"`
	CreatedAt           time.Time      `gorm:"column:created_at" json:"created_at"`
	UpdatedAt           time.Time      `gorm:"column:updated_at" json:"updated_at"`
}

func (Batch) TableName() string { return "batches" }

type ForecastBatchSlot struct {
	SlotNo    int       `gorm:"column:slot_no;primaryKey" json:"slot_no"`
	ModelType string    `gorm:"column:model_type" json:"model_type"`
	Capacity  int       `gorm:"column:capacity" json:"capacity"`
	BatchID   *string   `gorm:"column:batch_id" json:"batch_id"`
	Source    string    `gorm:"column:source" json:"source"`
	CreatedAt time.Time `gorm:"column:created_at" json:"created_at"`
	UpdatedAt time.Time `gorm:"column:updated_at" json:"updated_at"`
}

func (ForecastBatchSlot) TableName() string { return "forecast_batch_slots" }

type Unit struct {
	UnitID                   string     `gorm:"column:unit_id;primaryKey" json:"unit_id"`
	SerialNo                 *string    `gorm:"column:serial_no" json:"serial_no"`
	ForecastSerialNo         *string    `gorm:"column:forecast_serial_no" json:"forecast_serial_no"`
	BatchID                  string     `gorm:"column:batch_id" json:"batch_id"`
	SlotIndex                int        `gorm:"column:slot_index" json:"slot_index"`
	ModelType                string     `gorm:"column:model_type" json:"model_type"`
	ProductionLineID         *string    `gorm:"column:production_line_id" json:"production_line_id"`
	Status                   string     `gorm:"column:status" json:"status"`
	ContractNo               *string    `gorm:"column:contract_no" json:"contract_no"`
	Customer                 *string    `gorm:"column:customer" json:"customer"`
	DealerID                 *string    `gorm:"column:dealer_id" json:"dealer_id"`
	DealerName               *string    `gorm:"column:dealer_name" json:"dealer_name"`
	DueDate                  *time.Time `gorm:"column:due_date" json:"due_date"`
	SalesID                  *string    `gorm:"column:sales_id" json:"sales_id"`
	OrderRemark              *string    `gorm:"column:order_remark" json:"order_remark"`
	PromisedDueDate          *time.Time `gorm:"-" json:"promised_due_date"`
	IsLocked                 bool       `gorm:"column:is_locked" json:"is_locked"`
	LockedBy                 *string    `gorm:"column:locked_by" json:"locked_by"`
	LockedAt                 *time.Time `gorm:"column:locked_at" json:"locked_at"`
	IsContractPinned         bool       `gorm:"column:is_contract_pinned" json:"is_contract_pinned"`
	CreatedAt                time.Time  `gorm:"column:created_at" json:"created_at"`
	UpdatedAt                time.Time  `gorm:"column:updated_at" json:"updated_at"`
	BatchCode                *string    `gorm:"->;column:batch_code" json:"batch_code,omitempty"`
	BatchModelType           *string    `gorm:"->;column:batch_model_type" json:"batch_model_type,omitempty"`
	BatchStatus              *string    `gorm:"->;column:batch_status" json:"batch_status,omitempty"`
	BatchExpectedInboundDate *time.Time `gorm:"->;column:batch_expected_inbound_date" json:"batch_expected_inbound_date,omitempty"`
	FgExpectedInboundDate    *time.Time `gorm:"->;column:fg_expected_inbound_date" json:"fg_expected_inbound_date,omitempty"`
	ModelFamily              *string    `gorm:"->;column:model_family" json:"model_family,omitempty"`
	FgStatus                 *string    `gorm:"->;column:fg_status" json:"fg_status,omitempty"`
	FgRemark                 *string    `gorm:"->;column:fg_remark" json:"fg_remark,omitempty"`
	FgModel                  *string    `gorm:"->;column:fg_model" json:"fg_model,omitempty"`
	FgCustomer               *string    `gorm:"->;column:fg_customer" json:"fg_customer,omitempty"`
	FgDealer                 *string    `gorm:"->;column:fg_dealer" json:"fg_dealer,omitempty"`
	FgContractNo             *string    `gorm:"->;column:fg_contract_no" json:"fg_contract_no,omitempty"`
	FgSalesID                *string    `gorm:"->;column:fg_sales_id" json:"fg_sales_id,omitempty"`
}

func (Unit) TableName() string { return "units" }

type ProductionLine struct {
	ProductionLineID string    `gorm:"column:line_id;primaryKey" json:"production_line_id"`
	LineID           string    `gorm:"-" json:"line_id"`
	LineNo           int       `gorm:"column:display_order" json:"line_no"`
	LineName         string    `gorm:"column:line_name" json:"line_name"`
	Status           string    `gorm:"column:status" json:"status"`
	CurrentBatchID   *string   `gorm:"column:current_batch_id" json:"current_batch_id"`
	ModelType        *string   `gorm:"column:model_type" json:"model_type"`
	Region           *string   `gorm:"column:region" json:"region"`
	Units            []Unit    `gorm:"-" json:"units,omitempty"`
	Batches          []Batch   `gorm:"-" json:"batches,omitempty"`
	CreatedAt        time.Time `gorm:"column:created_at" json:"created_at"`
	UpdatedAt        time.Time `gorm:"column:updated_at" json:"updated_at"`
}

func (ProductionLine) TableName() string { return "production_lines" }

type SystemConfig struct {
	ConfigKey   string         `gorm:"column:config_key;primaryKey" json:"config_key"`
	ConfigValue datatypes.JSON `gorm:"column:config_value" json:"config_value"`
	Description *string        `gorm:"column:description" json:"description"`
	UpdatedBy   string         `gorm:"column:updated_by" json:"updated_by"`
	UpdatedAt   time.Time      `gorm:"column:updated_at" json:"updated_at"`
}

func (SystemConfig) TableName() string { return "system_config" }

type ProductionQueue struct {
	QueueID    uint64         `gorm:"column:queue_id;primaryKey;autoIncrement" json:"queue_id"`
	ModelType  string         `gorm:"column:model_type" json:"model_type"`
	ContractNo *string        `gorm:"column:contract_no" json:"contract_no"`
	Payload    datatypes.JSON `gorm:"column:payload" json:"payload"`
	Status     string         `gorm:"column:status" json:"status"`
	Priority   int            `gorm:"column:priority" json:"priority"`
	CreatedAt  time.Time      `gorm:"column:created_at" json:"created_at"`
	UpdatedAt  time.Time      `gorm:"column:updated_at" json:"updated_at"`
}

func (ProductionQueue) TableName() string { return "production_queue" }

type OperationLog struct {
	LogID      uint64         `gorm:"column:log_id;primaryKey;autoIncrement" json:"log_id"`
	Actor      string         `gorm:"column:actor" json:"actor"`
	Action     string         `gorm:"column:action" json:"action"`
	TargetType string         `gorm:"column:target_type" json:"target_type"`
	TargetID   string         `gorm:"column:target_id" json:"target_id"`
	Detail     datatypes.JSON `gorm:"column:detail" json:"detail"`
	CreatedAt  time.Time      `gorm:"column:created_at" json:"created_at"`
}

func (OperationLog) TableName() string { return "operation_log" }

type ContractUnit struct {
	ContractNo string    `json:"contract_no"`
	Customer   string    `json:"customer"`
	DealerName string    `json:"dealer_name"`
	ModelName  string    `json:"model_name"`
	ModelType  string    `json:"model_type"`
	DueDate    time.Time `json:"due_date"`
	SalesID    string    `json:"sales_id"`
	Remark     string    `json:"remark"`
}
