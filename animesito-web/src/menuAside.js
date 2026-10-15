import { mdiBrushVariant, mdiCogOutline, mdiImageMultipleOutline } from '@mdi/js'

// Sidebar entries. `jfast new view` inserts generated modules at the marker.
//
// Line comments, not a block comment: the marker ends with */.
export default [
  { to: '/', icon: mdiBrushVariant, label: 'Imagen' },
  { to: '/galeria', icon: mdiImageMultipleOutline, label: 'Galería' },
  { to: '/ajustes', icon: mdiCogOutline, label: 'Ajustes' },
  /*nuevoModulo*/
]
