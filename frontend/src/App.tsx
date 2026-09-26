import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, Navigate, RouterProvider, type RouteObject } from 'react-router'
import { AppShell } from '@/components/layout/AppShell'
import { Placeholder } from '@/pages/Placeholder'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/rules" replace /> },
      { path: 'rules', element: <Placeholder title="Rules" /> },
      { path: 'playground', element: <Placeholder title="Playground" /> },
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
    </QueryClientProvider>
  )
}
