import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, Navigate, RouterProvider, type RouteObject } from 'react-router'
import { AppShell } from '@/components/layout/AppShell'
import { Toaster } from '@/components/ui/sonner'
import { PlaygroundPage } from '@/pages/PlaygroundPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { TestsPage } from '@/pages/TestsPage'
import { NewRulePage } from '@/pages/rules/NewRulePage'
import { RuleDetailPage } from '@/pages/rules/RuleDetailPage'
import { RulesPage } from '@/pages/rules/RulesPage'
import { TranslatePage } from '@/pages/translate/TranslatePage'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/rules" replace /> },
      { path: 'rules', element: <RulesPage /> },
      { path: 'rules/new', element: <NewRulePage /> },
      { path: 'rules/translate', element: <TranslatePage /> },
      { path: 'rules/:ruleId', element: <RuleDetailPage /> },
      { path: 'playground', element: <PlaygroundPage /> },
      { path: 'tests', element: <TestsPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]

const queryClient = new QueryClient()
const router = createBrowserRouter(routes)

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster closeButton />
    </QueryClientProvider>
  )
}
