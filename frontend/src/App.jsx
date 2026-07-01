import React from "react";
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Accounts from "./pages/Accounts.jsx";
import Campaigns from "./pages/Campaigns.jsx";
import Contacts from "./pages/Contacts.jsx";
import Inbox from "./pages/Inbox.jsx";
import Groups from "./pages/Groups.jsx";
import Statuses from "./pages/Statuses.jsx";
import Templates from "./pages/Templates.jsx";
import Blacklist from "./pages/Blacklist.jsx";
import KeywordRules from "./pages/KeywordRules.jsx";
import AccountSchedules from "./pages/AccountSchedules.jsx";
import Journals from "./pages/Journals.jsx";
import Files from "./pages/Files.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="accounts" element={<Accounts />} />
        <Route path="campaigns" element={<Campaigns />} />
        <Route path="contacts" element={<Contacts />} />
        <Route path="inbox" element={<Inbox />} />
        <Route path="groups" element={<Groups />} />
        <Route path="statuses" element={<Statuses />} />
        <Route path="templates" element={<Templates />} />
        <Route path="blacklist" element={<Blacklist />} />
        <Route path="keyword-rules" element={<KeywordRules />} />
        <Route path="account-schedules" element={<AccountSchedules />} />
        <Route path="journals" element={<Journals />} />
        <Route path="files" element={<Files />} />
        <Route path="*" element={<div className="text-slate-400">صفحه یافت نشد</div>} />
      </Route>
    </Routes>
  );
}
