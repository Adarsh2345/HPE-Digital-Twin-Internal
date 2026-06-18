import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'

export default function Layout() {
  const [search, setSearch] = useState('')

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header search={search} onSearchChange={setSearch} />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet context={{ search }} />
        </main>
      </div>
    </div>
  )
}
