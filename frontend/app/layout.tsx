import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Toaster } from '@/components/ui/sonner'
import './globals.css'

export const metadata: Metadata = {
  title: 'AgentQA Cloud — AI Agent Evaluation Platform',
  description:
    'Run, score, and trace your AI support agent against regression scenarios. Track pass rates, policy compliance, prompt-injection resistance, latency, and cost.',
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#111417',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background font-sans antialiased">
        {children}
        <Toaster position="top-right" />
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
