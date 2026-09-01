import { useEffect, useState } from 'react'
import {
  ActivityIndicator,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import * as AppleAuthentication from 'expo-apple-authentication'
import { StatusBar } from 'expo-status-bar'
import { GoogleSignin } from '@react-native-google-signin/google-signin'
import { api, getToken, setToken } from './api'

GoogleSignin.configure({
  webClientId: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID,
  iosClientId: process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID,
})

export default function App() {
  const [user, setUser] = useState(null)
  const [booting, setBooting] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getToken()
      .then((t) => (t ? api.getMe() : null))
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setBooting(false))
  }, [])

  const afterToken = async (access) => {
    await setToken(access)
    setUser(await api.getMe())
  }

  const onEmailLogin = async () => {
    setError('')
    try {
      const { access_token } = await api.login(username, password)
      await afterToken(access_token)
    } catch (e) {
      setError(e.message)
    }
  }

  const onGoogle = async () => {
    setError('')
    try {
      await GoogleSignin.hasPlayServices()
      const result = await GoogleSignin.signIn()
      const idToken = result?.data?.idToken || result?.idToken
      if (!idToken) throw new Error('Google did not return an ID token')
      const { access_token } = await api.loginGoogle(idToken)
      await afterToken(access_token)
    } catch (e) {
      setError(e.message)
    }
  }

  const onApple = async () => {
    setError('')
    try {
      const cred = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        ],
      })
      const { access_token } = await api.loginApple(cred.identityToken)
      await afterToken(access_token)
    } catch (e) {
      if (e.code !== 'ERR_REQUEST_CANCELED') setError(e.message)
    }
  }

  const onSend = async () => {
    if (!message.trim()) return
    setBusy(true)
    setError('')
    try {
      const session = await api.createSession(message.slice(0, 80))
      const result = await api.chat(session.id, message)
      setReply(result.response)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (booting) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator color="#d97757" />
      </SafeAreaView>
    )
  }

  if (!user) {
    return (
      <SafeAreaView style={styles.wrap}>
        <StatusBar style="light" />
        <Text style={styles.h1}>LocalAI Agent</Text>
        <Text style={styles.sub}>Email, Google, or Apple sign-in</Text>
        <TextInput style={styles.input} placeholder="Username or email" placeholderTextColor="#888" value={username} onChangeText={setUsername} autoCapitalize="none" />
        <TextInput style={styles.input} placeholder="Password" placeholderTextColor="#888" value={password} onChangeText={setPassword} secureTextEntry />
        {error ? <Text style={styles.err}>{error}</Text> : null}
        <Pressable style={styles.btn} onPress={onEmailLogin}><Text style={styles.btnText}>Sign in</Text></Pressable>
        <Pressable style={styles.oauth} onPress={onGoogle}><Text style={styles.btnText}>Continue with Google</Text></Pressable>
        {Platform.OS === 'ios' && (
          <AppleAuthentication.AppleAuthenticationButton
            buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
            buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.WHITE}
            cornerRadius={8}
            style={{ width: '100%', height: 44, marginTop: 8 }}
            onPress={onApple}
          />
        )}
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView style={styles.wrap}>
      <StatusBar style="light" />
      <Text style={styles.h1}>Hi {user.username}</Text>
      <ScrollView style={{ flex: 1 }}>
        {reply ? <Text style={styles.reply}>{reply}</Text> : null}
      </ScrollView>
      {error ? <Text style={styles.err}>{error}</Text> : null}
      <TextInput style={styles.input} placeholder="Message" placeholderTextColor="#888" value={message} onChangeText={setMessage} />
      <Pressable style={styles.btn} onPress={onSend} disabled={busy}>
        <Text style={styles.btnText}>{busy ? 'Working…' : 'Send'}</Text>
      </Pressable>
      <Pressable onPress={async () => { await setToken(null); setUser(null) }}>
        <Text style={styles.sub}>Sign out</Text>
      </Pressable>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: '#1a1a1a', padding: 20, gap: 10 },
  center: { flex: 1, backgroundColor: '#1a1a1a', alignItems: 'center', justifyContent: 'center' },
  h1: { color: '#ececec', fontSize: 24, fontWeight: '600' },
  sub: { color: '#a0a0a0', marginBottom: 8 },
  input: { backgroundColor: '#2a2a2a', color: '#ececec', borderRadius: 8, padding: 12 },
  btn: { backgroundColor: '#d97757', borderRadius: 8, padding: 12, alignItems: 'center' },
  oauth: { backgroundColor: '#333', borderRadius: 8, padding: 12, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '600' },
  err: { color: '#ef4444' },
  reply: { color: '#ececec', lineHeight: 22 },
})
