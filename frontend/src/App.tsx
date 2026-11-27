import { useEffect } from 'react'
import { createBrowserRouter, Navigate, RouterProvider, useNavigate } from 'react-router-dom'
import { ApiKeyDialog } from './components/ApiKeyDialog'
import { Layout } from './components/Layout'
import { ChatPage } from './pages/ChatPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { KnowledgePage } from './pages/KnowledgePage'
import { SettingsPage } from './pages/SettingsPage'

function Shell() {
  const navigate = useNavigate()
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        navigate('/')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])
  return (
    <>
      <Layout />
      <ApiKeyDialog />
    </>
  )
}

const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: '/', element: <ChatPage /> },
      { path: '/c/:conversationId', element: <ChatPage /> },
      { path: '/knowledge', element: <KnowledgePage /> },
      { path: '/datasets', element: <DatasetsPage /> },
      { path: '/settings', element: <SettingsPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
