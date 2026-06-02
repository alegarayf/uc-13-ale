import { Navigate } from "react-router-dom";

/** @deprecated Use /garden-rules with AI mode toggle */
export function GardenRulesExperiment() {
  return <Navigate to="/garden-rules?mode=ai" replace />;
}
