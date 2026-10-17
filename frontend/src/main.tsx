/* oxlint-disable react/only-export-components */
import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import '@xyflow/react/dist/style.css'
// Bootstrap custom result card renderers into ResultRendererRegistry
import './components/renderers'
import LiveApp from './LiveApp.tsx'
const RenderTestApp = lazy(() => import('./App.tsx'));
const renderTest = import.meta.env.DEV && new URLSearchParams(location.search).get('renderTest') === '1';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<p>Loading workspace…</p>}>
      {renderTest ? <RenderTestApp /> : <LiveApp />}
    </Suspense>
  </StrictMode>,
)
