import { Outlet } from "react-router-dom";
import { Header } from "./Header";
import { SideNav } from "./SideNav";

export function AppLayout() {
  const handleAuthAction = () => {
    // Placeholder until authentication is implemented
    console.info("Auth action placeholder");
  };

  return (
    <div className="app-shell">
      <Header onAuthAction={handleAuthAction} />
      <div className="app-body">
        <SideNav />
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
