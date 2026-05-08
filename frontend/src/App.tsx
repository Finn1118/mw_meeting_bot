import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { Calendar } from './pages/Calendar'
import { ConversationDetail } from './pages/ConversationDetail'
import { ConversationsList } from './pages/ConversationsList'
import { NewMeeting } from './pages/NewMeeting'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<ConversationsList />} path="/" />
        <Route element={<Calendar />} path="/calendar" />
        <Route element={<NewMeeting />} path="/meetings/new" />
        <Route element={<ConversationDetail />} path="/meetings/:id" />
        <Route element={<Navigate replace to="/" />} path="*" />
      </Routes>
    </BrowserRouter>
  )
}

export default App
