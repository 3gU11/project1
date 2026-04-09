<template>
  <div class="virtual-list" :style="{ height: `${height}px` }" @scroll="onScroll">
    <div class="spacer" :style="{ height: `${totalHeight}px` }">
      <div class="content" :style="{ transform: `translateY(${offsetY}px)` }">
        <slot
          v-for="(item, idx) in visibleItems"
          :key="getItemKey(item, idx)"
          :item="item"
          :index="start + idx"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  items: any[]
  height: number
  itemHeight: number
  overscan?: number
  itemKey?: string
}>()

const scrollTop = ref(0)
const safeOverscan = computed(() => Math.max(1, props.overscan ?? 4))
const start = computed(() => Math.max(0, Math.floor(scrollTop.value / props.itemHeight) - safeOverscan.value))
const visibleCount = computed(() => Math.ceil(props.height / props.itemHeight) + safeOverscan.value * 2)
const end = computed(() => Math.min(props.items.length, start.value + visibleCount.value))
const visibleItems = computed(() => props.items.slice(start.value, end.value))
const offsetY = computed(() => start.value * props.itemHeight)
const totalHeight = computed(() => props.items.length * props.itemHeight)

const onScroll = (e: Event) => {
  const el = e.target as HTMLElement
  scrollTop.value = el.scrollTop
}

const getItemKey = (item: any, idx: number) => {
  if (props.itemKey) {
    const k = item?.[props.itemKey]
    if (k !== undefined && k !== null && String(k) !== '') return String(k)
  }
  return `${start.value + idx}`
}
</script>

<style scoped>
.virtual-list {
  overflow: auto;
  contain: content;
}
.spacer {
  position: relative;
}
.content {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  will-change: transform;
}
</style>
