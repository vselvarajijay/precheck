import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, Navigate, RouterProvider, type RouteObject } from 'react-router'
import { AppShell } from '@/components/layout/AppShell'
import { Toaster } from '@/components/ui/sonner'
import { Placeholder } from '@/pages/Placeholder'
import { PlaygroundPage } from '@/pages/PlaygroundPage'
import { NewRulePage } from '@/pages/rules/NewRulePage'
import { RuleDetailPage } from '@/pages/rules/RuleDetailPage'
import { RulesPage } from '@/pages/rules/RulesPage'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/rules" replace /> },
      { path: 'rules', element: <RulesPage /> },
      { path: 'rules/new', element: <NewRulePage /> },
      { path: 'rules/:ruleId', element: <RuleDetailPage /> },
      { path: 'playground', element: <PlaygroundPage /> },
      { path: 'tests', element: <Placeholder title="Tests" /> },
      { path: 'settings', element: <Placeholder title="Settings" /> },
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
