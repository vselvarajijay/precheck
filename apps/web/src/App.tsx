import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, Navigate, RouterProvider, type RouteObject } from 'react-router'
import { AppShell } from '@/app/AppShell'
import { Toaster } from '@/shared/ui/sonner'
import { AgentLabPage } from '@/features/lab/pages/AgentLabPage'
import { PlaygroundPage } from '@/features/playground/pages/PlaygroundPage'
import { SettingsPage } from '@/features/policy/pages/SettingsPage'
import { TestsPage } from '@/features/tests/pages/TestsPage'
import { NewRulePage } from '@/features/rules/pages/NewRulePage'
import { RuleDetailPage } from '@/features/rules/pages/RuleDetailPage'
import { RulesPage } from '@/features/rules/pages/RulesPage'
import { TranslatePage } from '@/features/translate/pages/TranslatePage'

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
      { path: 'lab', element: <AgentLabPage /> },
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
