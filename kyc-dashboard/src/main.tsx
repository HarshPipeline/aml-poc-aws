import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import CustomerKyc from "./pages/CustomerKyc";
import CustomerList from "./pages/CustomerList";
import Queue from "./aml/Queue";
import Investigation from "./aml/Investigation";
import Monitoring from "./aml/Monitoring";
import { Audit, Policies } from "./aml/Governance";
import "./index.css";
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/alerts" element={<Queue />} />
          <Route path="/investigations/:alertId" element={<Investigation />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/policies" element={<Policies />} />
          <Route path="/kyc" element={<CustomerList />} />
          <Route path="/kyc/:customerId" element={<CustomerKyc />} />
          <Route path="*" element={<Navigate to="/alerts" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
