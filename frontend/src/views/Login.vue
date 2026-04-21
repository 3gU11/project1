<template>
  <div class="login-container">
    <div class="login-card">
      <h2 class="title">🔐 V7ex 成品管理系统</h2>
      
      <el-tabs v-model="activeTab" class="login-tabs">
        <el-tab-pane label="登录系统" name="login">
          <el-form :model="loginForm" :rules="loginRules" ref="loginFormRef" label-position="top">
            <el-form-item label="账号" prop="username">
              <el-input v-model="loginForm.username" placeholder="请输入账号" :prefix-icon="User"></el-input>
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" show-password :prefix-icon="Lock" @keyup.enter="handleLogin(loginFormRef)"></el-input>
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="rememberMe">30天内免登录</el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" class="submit-btn" :loading="loading" @click="handleLogin(loginFormRef)">登录</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
        
        <el-tab-pane label="注册申请" name="register">
          <el-form :model="registerForm" :rules="registerRules" ref="registerFormRef" label-position="top">
            <el-form-item label="设置账号 (用户名)" prop="username">
              <el-input v-model="registerForm.username" placeholder="登录用的唯一ID"></el-input>
            </el-form-item>
            <el-form-item label="设置密码" prop="password">
              <el-input v-model="registerForm.password" type="password" placeholder="设置密码" show-password></el-input>
            </el-form-item>
            <el-form-item label="您的姓名 (真实姓名)" prop="name">
              <el-input v-model="registerForm.name" placeholder="请输入真实姓名"></el-input>
            </el-form-item>
            <el-form-item label="申请角色" prop="role">
              <el-select v-model="registerForm.role" placeholder="请选择申请角色" class="full-width">
                <el-option label="Boss (老板/管理)" value="Boss"></el-option>
                <el-option label="Admin (管理员)" value="Admin"></el-option>
                <el-option label="Sales (销售员)" value="Sales"></el-option>
                <el-option label="Prod (生产/仓管)" value="Prod"></el-option>
                <el-option label="Inbound (入库员)" value="Inbound"></el-option>
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="success" class="submit-btn" :loading="registerLoading" @click="handleRegister(registerFormRef)">提交注册申请</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { apiPost } from '../utils/request'
import { useReactiveFormDraft } from '../composables/useFormDraft'
import { requiredRule, requiredSelectRule } from '../utils/formRules'

type LoginResponse = {
  access_token: string
  token_type?: string
  user: { username: string; role: string; name: string }
}

const router = useRouter()
const userStore = useUserStore()

const activeTab = ref('login')
const loading = ref(false)
const registerLoading = ref(false)
const rememberMe = ref(true)

const loginFormRef = ref<FormInstance>()
const loginForm = reactive({
  username: '',
  password: ''
})

const loginRules = reactive<FormRules>({
  username: [requiredRule('账号')],
  password: [requiredRule('密码')]
})

const registerFormRef = ref<FormInstance>()
const registerForm = reactive({
  username: '',
  password: '',
  name: '',
  role: ''
})

const registerRules = reactive<FormRules>({
  username: [requiredRule('账号')],
  password: [requiredRule('密码')],
  name: [requiredRule('真实姓名')],
  role: [requiredSelectRule('角色')]
})

const loginDraft = useReactiveFormDraft('login:form', loginForm, {
  omitKeys: ['password'],
})
const registerDraft = useReactiveFormDraft('login:register', registerForm, {
  omitKeys: ['password'],
})

const handleLogin = async (formEl: FormInstance | undefined) => {
  if (!formEl) return
  await formEl.validate(async (valid) => {
    if (valid) {
      loading.value = true
      try {
        // FastAPI OAuth2PasswordBearer expects form data, not JSON
        const params = new URLSearchParams()
        params.append('username', loginForm.username)
        params.append('password', loginForm.password)

        const response = await apiPost<LoginResponse>('/auth/login', params, {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        })
        
        const { access_token, user } = response
        userStore.login(user, access_token, rememberMe.value)
        loginDraft.clearDraft()
        
        ElMessage.success(`登录成功！欢迎 ${user.name}`)
        router.push('/')
      } catch (error) {
        // Error handling is mostly done in interceptor, but we can catch local ones here
        console.error('Login error', error)
      } finally {
        loading.value = false
      }
    }
  })
}

const handleRegister = async (formEl: FormInstance | undefined) => {
  if (!formEl) return
  await formEl.validate(async (valid) => {
    if (valid) {
      registerLoading.value = true
      try {
        await apiPost('/users/register', registerForm)
        ElMessage.success('注册成功，请等待管理员审核')
        registerDraft.clearDraft()
        activeTab.value = 'login'
        registerForm.username = ''
        registerForm.password = ''
        registerForm.name = ''
        registerForm.role = ''
      } catch (error) {
        console.error('Register error', error)
      } finally {
        registerLoading.value = false
      }
    }
  })
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background-color: #fbfbfd;
  background-image: radial-gradient(circle at 10% 20%, rgba(10, 115, 251, 0.05) 0%, rgba(255,255,255,0) 90%), radial-gradient(circle at 90% 80%, rgba(220,230,240,0.3) 0%, rgba(255,255,255,0) 80%);
}

.login-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  padding: 32px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow: 0 20px 40px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02);
  width: 100%;
  max-width: 420px;
}

.title {
  text-align: center;
  margin-bottom: 28px;
  color: #1d1d1f;
  font-weight: 700;
  font-size: 24px;
  letter-spacing: -0.02em;
}

.login-tabs {
  margin-top: 20px;
}

.full-width {
  width: 100%;
}

.submit-btn {
  width: 100%;
  margin-top: 8px;
  padding: 10px 0;
  font-size: 16px;
  border-radius: 8px;
  height: 42px;
}
</style>
