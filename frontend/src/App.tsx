import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Spinner } from './components/ui'
import { AppLayout, AuthLayout } from './layouts/Layouts'

const Login = lazy(() => import('./pages/Login'))
const Register = lazy(() => import('./pages/Register'))
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'))
const ResetPassword = lazy(() => import('./pages/ResetPassword'))
const Consent = lazy(() => import('./pages/Consent'))
const CheckIn = lazy(() => import('./pages/CheckIn'))
const Chat = lazy(() => import('./pages/Chat'))
const Support = lazy(() => import('./pages/Support'))
const Home = lazy(() => import('./pages/Home'))
const Reviewer = lazy(() => import('./pages/Reviewer'))
const Doctor = lazy(() => import('./pages/Doctor'))
const AskDoctor = lazy(() => import('./pages/AskDoctor'))

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
        </Route>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Home />} />
          <Route path="/consent" element={<Consent />} />
          <Route path="/check-in" element={<CheckIn />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/support" element={<Support />} />
          <Route path="/reviewer" element={<Reviewer />} />
          <Route path="/doctor" element={<Doctor />} />
          <Route path="/talk-to-a-doctor" element={<AskDoctor />} />
          <Route path="*" element={<Home />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
