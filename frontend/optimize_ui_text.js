const fs = require('fs');
const path = require('path');

const VIEWS_DIR = "d:\\trae_projects\\V7change\\V7ex\\frontend\\src\\views";

const files = [
    "BossPlanning.vue", "ContractManage.vue", "Inbound.vue", "InventoryQuery.vue",
    "LogViewer.vue", "MachineArchive.vue", "MachineEdit.vue", "OrderAllocation.vue",
    "SalesOrder.vue", "ShippingReview.vue", "Traceability.vue", "UserManagement.vue",
    "WarehouseDashboard.vue"
];

const COLOR_MAP = {
    "#1f2937": "var(--color-gray-800)",
    "#111827": "var(--color-gray-900)",
    "#303133": "var(--text-color-primary)",
    "#333": "var(--text-color-primary)",
    "#606266": "var(--text-color-secondary)",
    "#6b7280": "var(--color-gray-500)",
    "#64748b": "var(--color-gray-500)",
    "#334155": "var(--color-gray-700)",
    "#374151": "var(--color-gray-700)",
    "#475569": "var(--color-gray-700)",
    "#9ca3af": "var(--color-gray-400)",
    "#cbd5e1": "var(--color-gray-300)",
    "#e5e7eb": "var(--color-gray-200)",
    "#ebeef5": "var(--border-color-light)",
    "#eef2f7": "var(--border-color-light)",
    "#f3f4f6": "var(--color-gray-100)",
    "#f5f7fa": "var(--color-gray-50)",
    "#f8fafc": "var(--color-gray-50)",
    "#f9fafb": "var(--color-gray-50)",
    "#ffffff": "var(--panel-bg)",
    "#fff": "var(--panel-bg)",
    
    "#eff6ff": "var(--color-primary-50)",
    "#dbeafe": "var(--color-primary-100)",
    "#409eff": "var(--color-primary-500)",
    "#3b82f6": "var(--color-primary-500)",
    "#2563eb": "var(--color-primary-600)",
    "#1d4ed8": "var(--color-primary-700)",
};

const TEXT_REPLACEMENTS = {
    "请选择...": "请选择",
    "请输入...": "请输入",
    "刷新": "刷新数据",
    "刷新数据数据": "刷新数据", 
    "重置": "重置条件",
    "确定": "确认操作",
    "取消": "取消操作",
    
    "🏢 合同管理": "🏢 销售合同管理",
    "💡 在录入未来合同、老板审批后，将流转至到当下单环节。": "💡 提示：录入的新合同在审批通过后，将自动流转至生产统筹与下单环节。",
    "➕ 新增合同 (批量录入)": "➕ 录入新合同 (批量)",
    "合同号将自动生成": "系统自动生成合同号",
    "要求交期": "期望交付日期",
    "客户名 (Customer)": "客户名称",
    "代理商 (Agent)": "代理商名称",
    "📎 合同附件 (可选)": "📎 附加合同文件 (可选)",
    "请在下方表格中添加机型，支持同一机型添加多行（例如一行标准、一行加高）。": "请在下方清单中添加设备机型。支持同一机型添加多条记录（例如：标准版与加高版分开录入）。",
    "加高?": "是否加高",
    "单行备注": "设备备注",
    "+ 添加机型行": "+ 添加设备型号",
    "合同总备注": "合同全局备注",
    "可选，应用于所有条目": "选填，将应用于该合同下的所有设备条目",
    "💾 保存所有合同条目": "💾 保存并提交合同",
    "🔥 紧急处理 [2月内]": "🔥 紧急交付 (60天内)",
    "📘 近期规划 [2月内]": "📘 近期规划 (60天内)",
    "📋 全景视图": "📋 所有合同视图",
    "选择合同号进行操作": "请选择目标合同进行状态变更",

    "📜 交易日志": "📜 系统交易日志",
    
    "📥 入库作业": "📥 设备入库作业",
    "🏭 机台入库 (Machine Inbound)": "🏭 设备扫描入库",
    "🏭 机台入库模块 (扫描入库)": "设备入库登记",
    "扫描批次号/流水号": "请输入批次号或流水号进行检索",
    "待入库清单 (": "待入库设备清单 (",
    "当前已勾选：": "已选择入库设备：",
    "💟 请选择目标库位进行入库(点击库位按钮确认)": "🎯 请选择目标库位（点击下方库位即确认入库）",
    "快速定位库位，如 A03 / B12": "请输入库位编号快速检索（例如：A03）",
    "请先在上方勾选待入库机台，库位按钮将自动显示。": "请先从上方清单中勾选需要入库的设备，系统将自动显示可用库位。",
    "📋 跟踪单导入 (Tracking Import)": "📋 批量导入跟踪单",
    "📤 上传新跟踪单": "📤 上传跟踪单据",
    "🔍 解析并追加到待入库清单": "🔍 解析文件并追加至待入库清单",
    "📝 待入库数据审核 (DB Staging)": "📝 待入库数据核对",
    "💾 保存本页编辑": "💾 保存当前页修改",
    
    "👥 用户注册审核与管理": "👥 账号与权限管理",
    "总用户数": "总账号数",
    "活跃用户": "活跃账号",
    "所有用户列表": "系统账号列表",
    "老板 (Boss)": "老板 (Boss)",
    "管理员 (Admin)": "系统管理员 (Admin)",
    "销售 (Sales)": "销售专员 (Sales)",
    "生产 (Prod)": "生产专员 (Prod)",
    "库管 (Inbound)": "仓库管理员 (Inbound)",
    "暂无待审核申请": "暂无待审核的账号申请",

    "👑 生产统筹 & 订单资源分配": "👑 生产统筹与订单资源分配",
    "📄 待审合同": "📄 待审核合同",
    "🎯 待规划": "🎯 待规划合同",
    "📦 现有订单": "📦 现有执行订单",
    "暂无合同关联订单": "当前暂无与合同关联的订单",
    "暂无独立订单": "当前暂无独立订单",
    "👈 请从左侧选择一个项目以查看详情": "👈 请从左侧列表中选择一个项目以查看详细信息",
    "🚀 前往规划": "🚀 进入生产规划",
    "❌ 驳回/取消": "❌ 驳回或取消合同",
    "🎯 规划详情 (现货/批次分配)": "🎯 生产规划详情 (现货与批次分配)",
    "💾 保存规划 (Save Plan)": "💾 保存当前规划",

    "📊 库存比例(看板)": "📊 实时库存比例分布",
    "仅显示加高 (High Only)": "仅查看加高型号",
    "📦 当前总库存 (Total)": "📦 当前系统总库存",
    "✅ 在库 (In Stock)": "✅ 已入库可用",
    "⏳ 待入库 (Pending)": "⏳ 待入库确认",
    "📄 详细清单 (Detailed List)": "📄 库存设备详细清单",
    "搜索流水号/机型/批次号...": "请输入流水号、机型或批次号进行检索...",

    "📦 订单配货与发货规划": "📦 订单配货与发货调度",
    "🔍 筛选条件": "🔍 订单检索条件",
    "配货进度": "配货完成进度",
    "暂无配货记录": "当前订单暂无配货记录",
    "操作：扫描条码以锁定机器": "操作提示：请扫描设备条码进行配货锁定",
    "扫描或输入机器条码(流水号)...": "请输入或扫描设备流水号...",

    "🚚 发货复核": "🚚 订单发货复核",
    "请选择订单查看详情": "请选择需要复核的订单以查看详情",
    "✅ 确认发货": "✅ 确认执行发货",
    
    "📊 汇总与追溯": "📊 数据汇总与产品追溯",
    
    "📂 机台档案": "📂 设备生命周期档案",
    
    "🛠️ 机台编辑": "🛠️ 设备信息维护",
};

function processFile(filepath) {
    let content = fs.readFileSync(filepath, 'utf-8');

    // 1. Replace Colors in <style>
    const styleMatch = content.match(/<style[^>]*>([\s\S]*?)<\/style>/);
    if (styleMatch) {
        let styleContent = styleMatch[1];
        
        for (const [oldColor, newVar] of Object.entries(COLOR_MAP)) {
            const regex = new RegExp(oldColor, 'gi');
            styleContent = styleContent.replace(regex, newVar);
        }
        
        styleContent = styleContent.replace(/padding:\s*4px\s*8px/g, 'padding: var(--space-1) var(--space-2)');
        styleContent = styleContent.replace(/padding:\s*8px\s*12px/g, 'padding: var(--space-2) var(--space-3)');
        styleContent = styleContent.replace(/padding:\s*10px\s*12px/g, 'padding: var(--space-2) var(--space-3)');
        styleContent = styleContent.replace(/padding:\s*10px/g, 'padding: var(--space-2)');
        styleContent = styleContent.replace(/padding:\s*20px/g, 'padding: var(--space-4)');
        styleContent = styleContent.replace(/margin-top:\s*10px/g, 'margin-top: var(--space-2)');
        styleContent = styleContent.replace(/margin-bottom:\s*10px/g, 'margin-bottom: var(--space-2)');
        styleContent = styleContent.replace(/margin-top:\s*8px/g, 'margin-top: var(--space-2)');
        styleContent = styleContent.replace(/margin-bottom:\s*8px/g, 'margin-bottom: var(--space-2)');
        styleContent = styleContent.replace(/gap:\s*10px/g, 'gap: var(--space-2)');
        styleContent = styleContent.replace(/gap:\s*12px/g, 'gap: var(--space-3)');
        styleContent = styleContent.replace(/gap:\s*14px/g, 'gap: var(--space-3)');
        styleContent = styleContent.replace(/border-radius:\s*4px/g, 'border-radius: var(--radius-sm)');
        styleContent = styleContent.replace(/border-radius:\s*6px/g, 'border-radius: var(--radius-md)');
        styleContent = styleContent.replace(/border-radius:\s*8px/g, 'border-radius: var(--radius-lg)');
        
        content = content.substring(0, styleMatch.index) + 
                  content.substring(styleMatch.index, styleMatch.index + styleMatch[0].length).replace(styleMatch[1], styleContent) + 
                  content.substring(styleMatch.index + styleMatch[0].length);
    }

    // 2. Replace Text in <template>
    const templateMatch = content.match(/<template>([\s\S]*?)<\/template>/);
    if (templateMatch) {
        let templateContent = templateMatch[1];
        for (const [oldText, newText] of Object.entries(TEXT_REPLACEMENTS)) {
            templateContent = templateContent.split(oldText).join(newText);
        }
        content = content.substring(0, templateMatch.index) + 
                  '<template>' + templateContent + '</template>' + 
                  content.substring(templateMatch.index + templateMatch[0].length);
    }

    fs.writeFileSync(filepath, content, 'utf-8');
}

files.forEach(filename => {
    const filepath = path.join(VIEWS_DIR, filename);
    if (fs.existsSync(filepath)) {
        processFile(filepath);
        console.log(`Processed ${filename}`);
    } else {
        console.log(`Skipped ${filename} (not found)`);
    }
});
