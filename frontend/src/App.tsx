import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { Dashboard } from "./pages/Dashboard";
import { GardenRules } from "./pages/GardenRules";
import { GardenRulesExperiment } from "./pages/GardenRulesExperiment";
import { MyGarden } from "./pages/MyGarden";
import { Profile } from "./pages/Profile";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="profile" element={<Profile />} />
          <Route path="my-garden" element={<MyGarden />} />
          <Route path="garden-rules" element={<GardenRules />} />
          <Route path="garden-rules/ai" element={<GardenRulesExperiment />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
