import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState, useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { useTranslation } from '@/contexts/LanguageContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Mail, Lock, Filter, Sparkles, BarChart3, Users } from 'lucide-react'
import { motion } from 'framer-motion'
import React from 'react'

export const Route = createFileRoute('/login')({
  component: LoginPage,
})

function LoginPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { login, loginWithSSO, isAuthenticated, isLoading } = useAuthStore()
  
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (isAuthenticated) {
      navigate({ to: '/' })
    }
  }, [isAuthenticated, navigate])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    
    try {
      await login(email, password)
      navigate({ to: '/' })
    } catch (err) {
      setError(t('login.invalidCredentials'))
    }
  }

  const handleMicrosoftLogin = async () => {
    try {
      await loginWithSSO('microsoft')
    } catch (err) {
      setError(t('login.ssoFailed'))
    }
  }

  const features = [
    {
      icon: Filter,
      title: t('login.features.filtering.title'),
      description: t('login.features.filtering.description'),
    },
    {
      icon: Sparkles,
      title: t('login.features.aiMatching.title'),
      description: t('login.features.aiMatching.description'),
    },
    {
      icon: BarChart3,
      title: t('login.features.analytics.title'),
      description: t('login.features.analytics.description'),
    },
    {
      icon: Users,
      title: t('login.features.management.title'),
      description: t('login.features.management.description'),
    },
  ]

  return (
    <div className="min-h-screen flex">
      {/* Left Side - Login Form (25%) */}
      <motion.div 
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full lg:w-[25%] flex flex-col justify-between p-12 bg-white"
      >
        <div className="w-full max-w-md mx-auto flex-1 flex flex-col justify-center">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-[22px] font-bold text-gray-900 mb-1">
              {t('login.welcomeBack')}
            </h1>
            <p className="text-[13px] text-gray-500">
              {t('login.subtitle')}
            </p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleLogin} className="space-y-5">
            {/* Email Field */}
            <div className="space-y-2">
              <Label 
                htmlFor="email" 
                className="text-[10px] font-semibold text-gray-500 uppercase tracking-[0.1em]"
              >
                {t('login.emailLabel')}
              </Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  id="email"
                  type="email"
                  placeholder={t('login.emailPlaceholder')}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="pl-10 h-[42px] bg-white border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gray-900 focus:border-transparent"
                  required
                />
              </div>
            </div>

            {/* Password Field */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label 
                  htmlFor="password" 
                  className="text-[10px] font-semibold text-gray-500 uppercase tracking-[0.1em]"
                >
                  {t('login.passwordLabel')}
                </Label>
                <button
                  type="button"
                  className="text-[11px] text-gray-600 hover:text-gray-900 font-medium"
                  onClick={() => {/* Handle forgot password */}}
                >
                  {t('login.forgotPassword')}
                </button>
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  id="password"
                  type="password"
                  placeholder={t('login.passwordPlaceholder')}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-10 h-[42px] bg-white border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gray-900 focus:border-transparent"
                  required
                />
              </div>
            </div>

            {/* Error Message */}
            {error && (
              <motion.div 
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-red-50 border border-red-200 text-red-600 px-4 py-2.5 rounded-lg text-xs"
              >
                {error}
              </motion.div>
            )}

            {/* Sign In Button */}
            <Button
              type="submit"
              disabled={isLoading}
              className="w-full h-[44px] bg-[#1a1f2e] hover:bg-[#252b3d] text-white rounded-lg font-semibold text-[15px] transition-colors"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  {t('login.signingIn')}
                </span>
              ) : (
                t('login.signIn')
              )}
            </Button>

            {/* Divider */}
            <div className="relative py-4">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-center">
                <span className="px-4 bg-white text-[11px] text-gray-400 uppercase tracking-[0.1em]">
                  {t('login.orContinueWith')}
                </span>
              </div>
            </div>

            {/* Microsoft SSO Button */}
            <Button
              type="button"
              variant="outline"
              onClick={handleMicrosoftLogin}
              disabled={isLoading}
              className="w-full h-[44px] bg-white border border-gray-300 hover:bg-gray-50 rounded-lg font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                  {t('login.connecting')}
                </span>
              ) : (
                <>
                  <svg className="w-5 h-5 mr-2" viewBox="0 0 21 21">
                    <g fill="none">
                      <path d="M0 0h10v10H0z" fill="#f25022"/>
                      <path d="M11 0h10v10H11z" fill="#7fba00"/>
                      <path d="M0 11h10v10H0z" fill="#00a4ef"/>
                      <path d="M11 11h10v10H11z" fill="#ffb900"/>
                    </g>
                  </svg>
                  {t('login.microsoftConnect')}
                </>
              )}
            </Button>
          </form>
        </div>

        {/* Footer */}
        <div className="text-[11px] text-gray-400 text-center pt-8">
          {t('login.footer')}
        </div>
      </motion.div>

      {/* Right Side - Marketing Showcase (75%) */}
      <div className="hidden lg:flex lg:w-[75%] relative overflow-hidden bg-slate-900">
        {/* Background Image */}
        <div className="absolute inset-0">
          <img 
            src="/RH.jpg"
            alt="HR Background"
            className="w-full h-full object-cover opacity-30"
          />
          <div className="absolute inset-0 bg-slate-900/70" />
        </div>

        {/* Logo Top Right */}
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="absolute top-8 right-8"
        >
          <img 
            src="/sofrecom-meta-logo-small-2025.webp" 
            alt="Sofrecom" 
            className="h-10 w-auto"
          />
        </motion.div>

        {/* Main Content */}
        <div className="relative z-10 flex flex-col items-center justify-center w-full px-20 py-36">
          {/* Hero Section */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="text-center mb-24 max-w-2xl"
          >
            <h2 className="text-[32px] font-bold text-white mb-4 leading-tight">
              {t('login.heroTitle')}
            </h2>
            <p className="text-[15px] text-gray-300 max-w-[480px] mx-auto leading-relaxed">
              {t('login.heroDescription')}
            </p>
          </motion.div>

          {/* Feature Cards - 2x2 grid */}
          <div className="grid grid-cols-2 gap-5 max-w-3xl w-full mb-auto">
            {features.map((feature, index) => (
              <AnimatedFeatureCard
                key={feature.title}
                icon={feature.icon}
                title={feature.title}
                description={feature.description}
                index={index}
              />
            ))}
          </div>

          {/* Social Proof - Bottom Left */}
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.8 }}
            className="absolute bottom-10 left-10 flex items-center gap-4"
          >
            {/* Overlapping Avatars */}
            <div className="flex -space-x-3">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="w-11 h-11 rounded-full border-2 border-white bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center text-white text-xs font-semibold shadow-md"
                >
                  {String.fromCharCode(64 + i)}
                </div>
              ))}
            </div>
            <div>
              <p className="text-[12px] text-white font-bold tracking-[0.1em] uppercase">
                {t('login.socialProof')}
              </p>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  )
}

interface AnimatedFeatureCardProps {
  icon: React.ElementType
  title: string
  description: string
  index: number
}

function AnimatedFeatureCard({ icon: Icon, title, description, index }: AnimatedFeatureCardProps) {
  // Animation ordre : CV Filtering (0) → Management (3) → Analytics (2) → AI Matching (1)
  // Puis disparition, puis réapparition même ordre
  const animationOrder = [0, 3, 2, 1] // Ordre d'apparition
  const orderPosition = animationOrder.indexOf(index)
  const fromRight = index === 0 || index === 2
  const xStart = fromRight ? 100 : -100
  
  return (
    <motion.div
      initial={{ opacity: 0, x: xStart }}
      animate={{ 
        opacity: [0, 1, 1, 1, 1, 0],
        x: [xStart, 0, 0, 0, 0, xStart]
      }}
      transition={{
        duration: 10,
        times: [0, 0.15, 0.4, 0.7, 0.85, 1],
        repeat: Infinity,
        repeatDelay: 0.5,
        delay: orderPosition * 0.4,
        ease: "easeInOut"
      }}
      className="flex items-start gap-4 p-6 bg-slate-800/60 backdrop-blur-md border border-white/20 rounded-2xl hover:bg-slate-800/80 transition-all duration-300"
    >
      <div className="p-3 bg-white/10 rounded-xl flex-shrink-0">
        <Icon className="w-6 h-6 text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <h3 className="text-white font-bold text-[15px] mb-1">
          {title}
        </h3>
        <p className="text-gray-300 text-[13px]">
          {description}
        </p>
      </div>
    </motion.div>
  )
}
