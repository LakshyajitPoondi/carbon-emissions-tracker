import { BrowserRouter, Route, Routes } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import { AppStateProvider } from "./context/AppStateContext";
import { ConsumptionPage } from "./pages/ConsumptionPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SetupPage } from "./pages/SetupPage";

export default function App() {
  return (
    <AppStateProvider>
      <BrowserRouter>
        <NavBar />
        <Routes>
          <Route path="/" element={<SetupPage />} />
          <Route path="/consumption" element={<ConsumptionPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/reports" element={<ReportsPage />} />
        </Routes>
      </BrowserRouter>
    </AppStateProvider>
  );
}
