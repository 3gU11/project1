<template>
  <div class="login-page">
    <div class="card">
      <h2>V7ex 仓储移动端</h2>
      <van-tabs v-model:active="tabActive">
        <van-tab title="登录">
          <van-form @submit="onSubmit">
            <van-field v-model="username" name="username" label="账号" placeholder="请输入账号" :rules="[{ required: true, message: '请输入账号' }]" />
            <van-field v-model="password" type="password" name="password" label="密码" placeholder="请输入密码" :rules="[{ required: true, message: '请输入密码' }]" />
            <div style="margin-top: 12px">
              <van-button type="primary" block native-type="submit" :loading="loading">登录</van-button>
            </div>
          </van-form>
        </van-tab>
        <van-tab title="注册">
          <van-form @submit="onRegister">
            <van-field v-model="reg.name" name="name" label="姓名" placeholder="请输入姓名" :rules="[{ required: true, message: '请输入姓名' }]" />
            <van-field v-model="reg.username" name="username" label="账号" placeholder="请输入账号" :rules="[{ required: true, message: '请输入账号' }]" />
            <van-field v-model="reg.password" type="password" name="password" label="密码" placeholder="请输入密码" :rules="[{ required: true, message: '请输入密码' }]" />
            <van-field v-model="confirmPassword" type="password" name="confirmPassword" label="确认密码" placeholder="请再次输入密码" :rules="[{ required: true, message: '请再次输入密码' }]" />
            <van-field name="role" label="角色">
              <template #input>
                <van-radio-group v-model="reg.role" direction="horizontal">
                  <van-radio name="Inbound">入库员</van-radio>
                  <van-radio name="Prod">库管</van-radio>
                </van-radio-group>
              </template>
            </van-field>
            <div style="margin-top: 12px">
              <van-button type="primary" block native-type="submit" :loading="registerLoading">注册</van-button>
            </div>
          </van-form>
        </van-tab>
      </van-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { authApi } from '@/api/auth'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const router = useRouter()
const tabActive = ref(0)
const username = ref('')
const password = ref('')
const loading = ref(false)
const registerLoading = ref(false)
const confirmPassword = ref('')
const reg = ref({
  name: '',
  username: '',
  password: '',
  role: 'Inbound' as 'Inbound' | 'Prod',
})

const onSubmit = async () => {
  loading.value = true
  try {
    await userStore.login(username.value, password.value)
    showToast('登录成功')
    router.replace('/query')
  } finally {
    loading.value = false
  }
}

const onRegister = async () => {
  if (reg.value.password !== confirmPassword.value) {
    showToast('两次密码不一致')
    return
  }
  registerLoading.value = true
  try {
    await authApi.register({
      name: reg.value.name.trim(),
      username: reg.value.username.trim(),
      password: reg.value.password,
      role: reg.value.role,
    })
    showToast('注册成功，请等待管理员审核')
    tabActive.value = 0
    reg.value = { name: '', username: '', password: '', role: 'Inbound' }
    confirmPassword.value = ''
  } finally {
    registerLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

h2 {
  margin: 0 0 12px;
  text-align: center;
}
</style>
