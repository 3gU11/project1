# V7ex 仓储专用移动端前端计划

## 项目概述

基于现有后端API，专门为库管和入库员设计的移动端应用，提供简洁高效的操作界面，复用现有后端代码。

## 一、系统架构

### 1.1 整体架构
```
┌─────────────────┐    HTTP/HTTPS    ┌─────────────────┐
│  移动端应用      │ ◄────────────► │   后端服务      │
│  (Vue 3 + Vant) │                 │  (Python API)  │
└─────────────────┘                 └─────────────────┘
       ▲                                      │
       │                                    SQLite/
       │                                    MySQL
       └                                      │
                       移动设备
```

### 1.2 技术栈
- **前端框架**：Vue 3 + Composition API
- **UI组件库**：Vant 4（专为移动端优化）
- **状态管理**：Pinia（支持持久化）
- **路由**：Vue Router 4
- **构建工具**：Vite
- **网络请求**：Axios
- **扫码功能**：html5-qrcode 或 qr-scanner
- **离线支持**：Service Worker + IndexedDB
- **图标**：Vant Icon + 自定义SVG

### 1.3 项目结构
```
V7ex-Warehousing-Mobile/
├── public/
│   ├── manifest.json      # PWA配置
│   └── favicon.ico
├── src/
│   ├── api/              # API接口封装
│   │   ├── index.ts      # 请求配置
│   │   ├── inbound.ts    # 入库相关API
│   │   └── inventory.ts  # 库存相关API
│   ├── assets/           # 静态资源
│   │   └── styles/
│   │       ├── reset.css # 样式重置
│   │       └── theme.css # 主题样式
│   ├── components/        # 公共组件
│   │   ├── layout/       # 布局组件
│   │   ├── common/       # 通用组件
│   │   └── business/     # 业务组件
│   ├── hooks/            # 组合式函数
│   ├── router/           # 路由配置
│   ├── store/            # 状态管理
│   ├── utils/            # 工具函数
│   └── views/            # 页面组件
├── index.html
└── vite.config.ts
```

## 二、功能模块设计

### 2.1 角色权限设计
```typescript
// 用户角色类型
type UserRole = 'inbound' | 'warehouse' | 'admin'

// 角色权限配置
const rolePermissions = {
  inbound: {
    name: '入库员',
    allowedRoutes: ['/inbound', '/inventory-query'],
    features: ['scan-inbound', 'batch-upload', 'slot-select']
  },
  warehouse: {
    name: '库管',
    allowedRoutes: ['/inventory-query', '/slot-management', '/dashboard'],
    features: ['view-inventory', 'slot-check', 'scan-query', 'report-issue']
  }
}
```

### 2.2 核心功能模块

#### 1. 入库员模块
- **扫码入库**
  - 批次号扫描
  - 设备信息确认
  - 库位选择
  - 入库确认

- **批量录入**
  - Excel导入
  - 批次管理
  - 快速入库

#### 2.2 库管模块
- **库存查询**
  - 快速扫码查询
  - 库存概览
  - 筛选和排序

- **库位管理**
  - 库位状态查看
  - 扫码盘点
  - 异常上报

- **数据大屏**
  - 实时库位状态
  - 库存分布

## 三、页面设计

### 3.1 页面路由结构
```typescript
const routes = [
  {
    path: '/login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/layout/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: 'inbound',
        component: () => import('@/views/InboundWork.vue'),
        meta: { title: '入库作业', roles: ['inbound'] }
      },
      {
        path: 'inventory-query',
        component: () => import('@/views/InventoryQuery.vue'),
        meta: { title: '库存查询', roles: ['inbound', 'warehouse'] }
      },
      {
        path: 'slot-management',
        component: () => import('@/views/SlotManagement.vue'),
        meta: { title: '库位管理', roles: ['warehouse'] }
      },
      {
        path: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '库位大屏', roles: ['warehouse'] }
      },
      {
        path: 'profile',
        component: () => import('@/views/Profile.vue'),
        meta: { title: '个人中心' }
      }
    ]
  }
]
```

### 3.2 布局组件

#### 主布局（Layout.vue）
```vue
<template>
  <div class="app">
    <!-- 顶部导航栏 -->
    <van-nav-bar
      :title="pageTitle"
      left-arrow
      @click-left="goBack"
      fixed
    />
    
    <!-- 主内容区 -->
    <main class="main-content">
      <router-view />
    </main>
    
    <!-- 底部导航栏 -->
    <van-tabbar v-model="active" class="bottom-nav">
      <van-tabbar-item 
        v-for="tab in tabs" 
        :key="tab.path"
        :icon="tab.icon"
        :to="tab.path"
      >
        {{ tab.title }}
      </van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

// 根据角色显示不同的标签页
const active = computed(() => route.path)

const tabs = computed(() => {
  const role = userStore.userInfo?.role
  if (role === 'inbound') {
    return [
      { path: '/inbound', title: '入库', icon: 'cart-o' },
      { path: '/inventory-query', title: '查询', icon: 'search' },
      { path: '/profile', title: '我的', icon: 'user-o' }
    ]
  } else if (role === 'warehouse') {
    return [
      { path: '/inventory-query', title: '库存', icon: 'search' },
      { path: '/slot-management', title: '库位', icon: 'location-o' },
      { path: '/dashboard', title: '大屏', icon: 'bar-chart' },
      { path: '/profile', title: '我的', icon: 'user-o' }
    ]
  }
  return []
})

const pageTitle = computed(() => route.meta?.title || '')
</script>
```

### 3.3 入库作业页面

#### InboundWork.vue
```vue
<template>
  <div class="inbound-work">
    <!-- 工作模式切换 -->
    <van-tabs v-model="activeMode" sticky>
      <!-- 扫码入库 -->
      <van-tab title="扫码入库">
        <div class="scan-section">
          <ScanButton @success="onScanSuccess" />
          
          <!-- 扫码结果展示 -->
          <div v-if="scanResult" class="scan-result">
            <van-cell-group inset>
              <van-cell title="批次号" :value="scanResult.batchNo" />
              <van-cell title="机型" :value="scanResult.model" />
              <van-cell title="流水号" :value="scanResult.serialNo" />
              <van-cell title="配置" :value="scanResult.config" />
            </van-cell-group>
            
            <van-button 
              type="primary" 
              block 
              @click="confirmInbound"
              :disabled="!scanResult"
              style="margin-top: 16px"
            >
              确认入库
            </van-button>
          </div>
        </div>
        
        <!-- 待入库列表 -->
        <div class="pending-section">
          <van-divider>待入库设备</van-divider>
          <van-pull-refresh v-model="refreshing" @refresh="loadPendingList">
            <van-list
              v-model:loading="loading"
              finished
              finished-text="没有更多了"
            >
              <van-cell-group inset>
                <van-cell 
                  v-for="item in pendingList"
                  :key="item.id"
                  :title="item.batchNo"
                  :label="`${item.model} | ${item.serialNo}`"
                  is-link
                  @click="selectItem(item)"
                >
                  <template #extra>
                    <van-checkbox v-model="item.selected" />
                  </template>
                </van-cell>
              </van-cell-group>
            </van-list>
          </van-pull-refresh>
        </div>
        
        <!-- 库位选择弹窗 -->
        <van-popup 
          v-model:show="showSlotPicker" 
          position="bottom" 
          round
        >
          <div class="slot-picker-header">
            <h3>选择库位</h3>
            <van-search 
              v-model="slotKeyword" 
              placeholder="搜索库位编号"
            />
          </div>
          
          <div class="slot-grid">
            <div 
              v-for="slot in filteredSlots"
              :key="slot.code"
              class="slot-item"
              :class="{
                'available': slot.status === 'idle',
                'full': slot.status === 'full',
                'occupied': slot.status === 'occupied'
              }"
              @click="chooseSlot(slot)"
            >
              <div class="slot-code">{{ slot.code }}</div>
              <div class="slot-info">
                <span class="count">{{ slot.current }}/{{ slot.max }}</span>
              </div>
            </div>
          </div>
        </van-popup>
      </van-tab>
      
      <!-- 批量导入 -->
      <van-tab title="批量导入">
        <BatchUpload @success="onUploadSuccess" />
      </van-tab>
    </van-tabs>
  </div>
</template>
```

### 3.4 库存查询页面

#### InventoryQuery.vue
```vue
<template>
  <div class="inventory-query">
    <!-- 顶部操作区 -->
    <div class="header-actions">
      <van-button 
        type="primary" 
        icon="qr"
        @click="quickScan"
      >
        快速扫码
      </van-button>
    </div>
    
    <!-- 统计卡片 -->
    <van-grid :column-num="4" class="stats-grid" gutter="12">
      <van-grid-item icon="passed" text="总库存" :value="stats.total" />
      <van-grid-item icon="todo" text="待入库" :value="stats.pending" />
      <van-grid-item icon="location" text="在库" :value="stats.inStock" />
      <van-grid-item icon="warning" text="异常" :value="stats.error" />
    </van-grid>
    
    <!-- 搜索筛选 -->
    <div class="filter-section">
      <van-search
        v-model="keyword"
        placeholder="搜索机型或库位"
        @search="onSearch"
      />
      
      <div class="filter-chips">
        <van-chips 
          v-model="selectedModels" 
          max="3"
          @close="onModelRemove"
        >
          <van-chip 
            v-for="model in modelOptions"
            :key="model"
            :closeable="selectedModels.includes(model)"
          >
            {{ model }}
          </van-chip>
        </van-chips>
        
        <van-checkbox v-model="showHighOnly" shape="square">
          仅加高型号
        </van-checkbox>
      </div>
    </div>
    
    <!-- 库存列表 -->
    <van-pull-refresh v-model="refreshing" @refresh="loadInventory">
      <van-list
        v-model:loading="loading"
        :finished="finished"
        finished-text="没有更多了"
        @load="loadInventory"
      >
        <div class="inventory-list">
          <div 
            v-for="item in inventoryList"
            :key="item.id"
            class="inventory-item"
            @click="showDetail(item)"
          >
            <div class="item-header">
              <span class="model">{{ item.model }}</span>
              <van-tag :type="getItemTagType(item)">
                {{ getItemStatusText(item) }}
              </van-tag>
            </div>
            <div class="item-info">
              <span class="slot">{{ item.slotCode }}</span>
              <span class="count">{{ item.count }}台</span>
            </div>
          </div>
        </div>
      </van-list>
    </van-pull-refresh>
  </div>
</template>
```

### 3.5 库位管理页面

#### SlotManagement.vue
```vue
<template>
  <div class="slot-management">
    <!-- 筛选条件 -->
    <div class="filter-bar">
      <van-button plain @click="scanSlot">扫码盘点</van-button>
      <van-dropdown-menu>
        <van-dropdown-item 
          v-model="filterStatus"
          :options="statusOptions"
        />
      </van-dropdown-menu>
    </div>
    
    <!-- 库位网格 -->
    <div class="slot-grid-container">
      <div 
        v-for="section in groupedSlots"
        :key="section.name"
        class="slot-section"
      >
        <h3 class="section-title">{{ section.name }}</h3>
        <div class="slot-grid">
          <div 
            v-for="slot in section.slots"
            :key="slot.code"
            class="slot-card"
            :class="slot.status"
            @click="selectSlot(slot)"
          >
            <div class="slot-code">{{ slot.code }}</div>
            <div class="slot-count">
              <span class="current">{{ slot.current }}</span>
              <span class="separator">/</span>
              <span class="max">{{ slot.max }}</span>
            </div>
            <div class="slot-progress">
              <div 
                class="progress-bar"
                :style="{ width: getProgress(slot) + '%' }"
              />
            </div>
            <div v-if="slot.serialNos.length > 0" class="slot-items">
              <span 
                v-for="sn in slot.serialNos.slice(0, 2)"
                :key="sn"
                class="sn-item"
              >
                {{ sn.slice(-4) }}
              </span>
              <span v-if="slot.serialNos.length > 2" class="more">
                +{{ slot.serialNos.length - 2 }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 快速操作栏 -->
    <van-sticky position="bottom">
      <van-submit-bar>
        <van-button type="primary" @click="batchUpdate">
          批量更新 ({{ selectedSlots.length }})
        </van-button>
      </van-submit-bar>
    </van-sticky>
  </div>
</template>
```

### 3.6 公共组件

#### 扫码组件
```vue
<!-- components/common/ScanButton.vue -->
<template>
  <div class="scan-container">
    <van-button 
      type="primary" 
      block 
      round
      :loading="scanning"
      @click="startScan"
    >
      <van-icon name="qr" size="20" />
      {{ scanning ? '扫码中...' : '点击扫码' }}
    </van-button>
    
    <div v-if="showCamera" class="camera-container">
      <div id="qr-reader" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { showToast } from 'vant'
import { useInboundStore } from '@/store/inbound'

const props = defineProps({
  onSuccess: Function
})

const scanning = ref(false)
const showCamera = ref(false)
const inboundStore = useInboundStore()

const startScan = async () => {
  if (scanning.value) return
  
  scanning.value = true
  showCamera.value = true
  
  try {
    const html5QrCode = new Html5Qrcode("qr-reader")
    
    await html5QrCode.start(
      { facingMode: "environment" },
      { fps: 10, qrbox: { width: 250, height: 250 } },
      (decodedText) => {
        handleScanResult(decodedText)
        html5QrCode.stop()
        resetScan()
      },
      (errorMessage) => {
        // 忽略临时错误
      }
    )
  } catch (error) {
    showToast('相机启动失败')
    resetScan()
  }
}

const handleScanResult = (result) => {
  // 根据扫描结果类型处理
  if (result.startsWith('B')) {
    // 批次号
    inboundStore.scanBatch(result)
  } else if (result.startsWith('SN')) {
    // 流水号
    inboundStore.scanSerial(result)
  } else {
    // 其他类型
    props.onSuccess?.(result)
  }
}

const resetScan = () => {
  scanning.value = false
  showCamera.value = false
}
</script>
```

## 四、状态管理

### 4.1 入库状态管理
```typescript
// store/inbound.ts
export const useInboundStore = defineStore('inbound', {
  state: () => ({
    pendingList: [],          // 待入库列表
    selectedItems: [],        // 选中项
    scanResult: null,        // 扫码结果
    availableSlots: [],       // 可用库位
    currentMode: 'scan'       // 工作模式
  }),
  
  actions: {
    // 扫描批次号
    async scanBatch(batchNo) {
      try {
        const res = await inboundApi.getPendingList({ keyword: batchNo })
        this.pendingList = res.data
      } catch (error) {
        showToast('获取数据失败')
      }
    },
    
    // 选择待入库项
    selectItem(item) {
      const index = this.selectedItems.findIndex(i => i.id === item.id)
      if (index > -1) {
        this.selectedItems.splice(index, 1)
      } else {
        this.selectedItems.push(item)
      }
    },
    
    // 确认入库
    async confirmInbound(slotCode) {
      if (!this.selectedItems.length || !slotCode) {
        showToast('请选择设备和库位')
        return
      }
      
      try {
        const promises = this.selectedItems.map(item => 
          inboundApi.confirmInbound({
            batchNo: item.batchNo,
            serialNo: item.serialNo,
            slotCode
          })
        )
        
        await Promise.all(promises)
        showToast('入库成功')
        this.selectedItems = []
        this.loadPendingList()
      } catch (error) {
        showToast('入库失败')
      }
    },
    
    // 加载待入库列表
    async loadPendingList() {
      // 从API加载
    }
  },
  
  persist: {
    paths: ['selectedItems']
  }
})
```

### 4.2 库存状态管理
```typescript
// store/inventory.ts
export const useInventoryStore = defineStore('inventory', {
  state: () => ({
    inventoryList: [],        // 库存列表
    stats: {
      total: 0,
      pending: 0,
      inStock: 0,
      error: 0
    },
    filterOptions: {
      keyword: '',
      selectedModels: [],
      showHighOnly: false
    }
  }),
  
  actions: {
    // 加载库存数据
    async loadInventory() {
      const { keyword, selectedModels, showHighOnly } = this.filterOptions
      const res = await inventoryApi.getInventoryList({
        keyword,
        models: selectedModels,
        highOnly: showHighOnly
      })
      this.inventoryList = res.data.list
      this.stats = res.data.stats
    },
    
    // 快速扫码查询
    async quickScan(code) {
      const res = await inventoryApi.scanQuery(code)
      return res.data
    },
    
    // 筛选库存
    filterInventory(filters) {
      this.filterOptions = { ...this.filterOptions, ...filters }
      this.loadInventory()
    }
  }
})
```

## 五、API接口封装

### 5.1 请求配置
```typescript
// api/index.ts
import axios from 'axios'
import { showToast } from 'vant'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截
request.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截
request.interceptors.response.use(
  response => response.data,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      location.href = '/login'
    } else {
      showToast(error.message || '请求失败')
    }
    return Promise.reject(error)
  }
)

export default request
```

### 5.2 入库相关API
```typescript
// api/inbound.ts
export const inboundApi = {
  // 获取待入库列表
  getPendingList: (params) => 
    request.get('/inbound/pending', { params }),
  
  // 扫码确认设备信息
  scanMachine: (batchNo, serialNo) => 
    request.post('/inbound/scan', { batchNo, serialNo }),
  
  // 确认入库
  confirmInbound: (data) => 
    request.post('/inbound/confirm', data),
  
  // 批量导入
  batchUpload: (formData) => 
    request.post('/inbound/batch-upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }),
  
  // 获取可用库位
  getAvailableSlots: () => 
    request.get('/inbound/slots/available')
}
```

### 5.3 库存相关API
```typescript
// api/inventory.ts
export const inventoryApi = {
  // 获取库存列表
  getInventoryList: (params) => 
    request.get('/inventory/list', { params }),
  
  // 扫码查询
  scanQuery: (code) => 
    request.get('/inventory/scan', { params: { code } }),
  
  // 获取库位状态
  getSlotStatus: () => 
    request.get('/inventory/slot-status'),
  
  // 更新库位状态
  updateSlotStatus: (data) => 
    request.post('/inventory/slot-update', data),
  
  // 扫码盘点
  scanCheck: (data) => 
    request.post('/inventory/scan-check', data)
}
```

## 六、离线功能设计

### 6.1 Service Worker配置
```javascript
// sw.js
const CACHE_NAME = 'v7ex-warehousing-v1'
const CACHE_URLS = [
  '/',
  '/static/js/main.js',
  '/static/css/main.css'
]

// 安装Service Worker
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(CACHE_URLS))
  )
})

// 拦截请求
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        return response || fetch(event.request)
      })
  )
})
```

### 6.2 离线数据同步
```typescript
// utils/sync.ts
export class OfflineSync {
  private queue: any[] = []
  
  // 添加到离线队列
  addToQueue(action, data) {
    this.queue.push({ action, data, timestamp: Date.now() })
    this.saveToLocalStorage()
  }
  
  // 保存到本地存储
  saveToLocalStorage() {
    localStorage.setItem('offlineQueue', JSON.stringify(this.queue))
  }
  
  // 同步离线数据
  async sync() {
    if (navigator.onLine && this.queue.length > 0) {
      try {
        const response = await fetch('/api/sync', {
          method: 'POST',
          body: JSON.stringify(this.queue)
        })
        
        if (response.ok) {
          this.queue = []
          localStorage.removeItem('offlineQueue')
        }
      } catch (error) {
        console.error('同步失败:', error)
      }
    }
  }
}
```

## 七、性能优化

### 7.1 图片和资源优化
- 使用SVG图标代替图片
- 启用Gzip压缩
- CDN加速静态资源

### 7.2 代码优化
- 路由懒加载
- 组件按需引入
- 虚拟滚动（长列表）

### 7.3 缓存策略
- API响应缓存
- 本地数据缓存
- 静态资源缓存

## 八、测试计划

### 8.1 单元测试
- 组件渲染测试
- Vuex状态管理测试
- API接口测试

### 8.2 功能测试
- 扫码功能测试
- 离线功能测试
- 数据同步测试

### 8.3 兼容性测试
- iOS/Android设备
- 不同浏览器
- 网络环境测试

## 九、上线部署

### 9.1 构建配置
```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "build:prod": "vite build --mode production",
    "preview": "vite preview"
  }
}
```

### 9.2 环境配置
```typescript
// vite.config.ts
export default defineConfig({
  base: '/mobile/',  // 移动端独立部署路径
  build: {
    target: 'es2015',
    minify: 'terser',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['vue', 'vue-router', 'pinia'],
          vant: ['vant']
        }
      }
    }
  },
  plugins: [
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'V7ex仓储管理',
        short_name: 'V7ex',
        theme_color: '#1989fa'
      }
    })
  ]
})
```

## 十、开发计划

### 第一周：项目初始化
- [ ] 创建Vue项目
- [ ] 配置Vite和TypeScript
- [ ] 安装Vant和依赖
- [ ] 搭建基础布局
- [ ] 实现登录功能

### 第二周：入库功能开发
- [ ] 入库作业页面框架
- [ ] 扫码组件集成
- [ ] 设备列表展示
- [ ] 库位选择功能
- [ ] 批量导入功能

### 第三周：库存管理功能
- [ ] 库存查询页面
- [ ] 扫码查询功能
- [ ] 库位管理页面
- [ ] 数据大屏页面

### 第四周：优化和测试
- [ ] 性能优化
- [ ] 离线功能
- [ ] 真机测试
- [ ] Bug修复
- [ ] 上线部署

这套专门为仓储人员设计的移动端应用，将大大提高他们的工作效率，减少操作步骤，让日常入库和管理工作更加便捷。