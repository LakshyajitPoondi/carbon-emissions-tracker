import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AppStateProvider } from "./context/AppStateContext";
import { AuthProvider } from "./context/AuthContext";
import { AuthPage } from "./pages/AuthPage";
import { ConsumptionPage } from "./pages/ConsumptionPage";
import { DashboardPage } from "./pages/DashboardPage";
import { OrganizationOverviewPage } from "./pages/OrganizationOverviewPage";
import { ProductLibraryPage } from "./pages/ProductLibraryPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SetupPage } from "./pages/SetupPage";

export default function App() {
  return (
    <AuthProvider>
      <AppStateProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/login" element={<AuthPage />} />
              <Route element={<ProtectedRoute />}>
                <Route path="/" element={<SetupPage />} />
                <Route path="/consumption" element={<ConsumptionPage />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/overview" element={<OrganizationOverviewPage />} />
                <Route path="/products" element={<ProductLibraryPage />} />
                <Route path="/reports" element={<ReportsPage />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </AppStateProvider>
    </AuthProvider>
  );
}
