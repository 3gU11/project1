const fs = require('fs');
const path = require('path');

const VIEWS_DIR = "d:\\trae_projects\\V7change\\V7ex\\frontend\\src\\views";

const files = [
    "BossPlanning.vue", "ContractManage.vue", "Inbound.vue", "InventoryQuery.vue",
    "LogViewer.vue", "MachineArchive.vue", "MachineEdit.vue", "OrderAllocation.vue",
    "SalesOrder.vue", "ShippingReview.vue", "Traceability.vue", "UserManagement.vue",
    "WarehouseDashboard.vue", "Home.vue"
];

function processFile(filepath) {
    let content = fs.readFileSync(filepath, 'utf-8');

    const styleMatch = content.match(/<style[^>]*>([\s\S]*?)<\/style>/);
    if (styleMatch) {
        let styleContent = styleMatch[1];
        
        // 替换所有硬编码的 font-size
        styleContent = styleContent.replace(/font-size:\s*12px/g, 'font-size: var(--font-size-sm)');
        styleContent = styleContent.replace(/font-size:\s*13px/g, 'font-size: var(--font-size-sm)');
        styleContent = styleContent.replace(/font-size:\s*14px/g, 'font-size: var(--font-size-base)');
        styleContent = styleContent.replace(/font-size:\s*15px/g, 'font-size: var(--font-size-base)');
        styleContent = styleContent.replace(/font-size:\s*16px/g, 'font-size: var(--font-size-lg)');
        
        content = content.substring(0, styleMatch.index) + 
                  content.substring(styleMatch.index, styleMatch.index + styleMatch[0].length).replace(styleMatch[1], styleContent) + 
                  content.substring(styleMatch.index + styleMatch[0].length);
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
