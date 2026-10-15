import { createBrowserRouter, Outlet } from 'react-router-dom'

import AppLayout from '@/layouts/AppLayout.jsx'
import GalleryView from '@/views/GalleryView.jsx'
import ImageView from '@/views/ImageView.jsx'
import SettingsView from '@/views/SettingsView.jsx'

// Single local user, no sign-in: every route is public. The backend's
// localguard plugin is what keeps other origins and hosts out.
//
// Line comments, not a block comment: the marker below ends with */.
const routes = [
  { path: '/', element: <ImageView />, handle: { title: 'Imagen' } },
  { path: '/galeria', element: <GalleryView />, handle: { title: 'Galería' } },
  { path: '/ajustes', element: <SettingsView />, handle: { title: 'Ajustes' } },
  /*nuevaRuta*/
]

export default createBrowserRouter([
  {
    element: (
      <AppLayout>
        <Outlet />
      </AppLayout>
    ),
    children: routes,
  },
])
