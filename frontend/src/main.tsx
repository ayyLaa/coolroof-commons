import React from 'react'
import ReactDOM from 'react-dom/client'
import { createTheme, MantineProvider } from '@mantine/core'
import { BrowserRouter } from 'react-router-dom'
import '@mantine/core/styles.css'
import '@mantine/charts/styles.css'
import 'leaflet/dist/leaflet.css'
import App from './App'
import { SelectedRoofProvider } from './hooks/useSelectedRoof'
import './app.css'

ReactDOM.createRoot(document.getElementById('app')!).render(
  <React.StrictMode>
    <MantineProvider
      forceColorScheme="light"
      theme={createTheme({
        primaryColor: 'teal',
        defaultRadius: 'md',
        fontFamily: 'Inter, Segoe UI, sans-serif',
        headings: { fontFamily: 'Inter, Segoe UI, sans-serif', fontWeight: '600' },
      })}
    >
      <BrowserRouter>
        <SelectedRoofProvider>
          <App />
        </SelectedRoofProvider>
      </BrowserRouter>
    </MantineProvider>
  </React.StrictMode>,
)
