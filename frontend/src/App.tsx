import { Route, Routes } from 'react-router-dom';
import styles from './App.module.css';

function Home() {
  return (
    <main className={styles.shell}>
      <h1>CorpLunch</h1>
    </main>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  );
}
