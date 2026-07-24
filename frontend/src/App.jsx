import React from "react";
import { Routes, Route } from "react-router-dom";
import { Toaster, ConfirmHost } from "./ui/toast.jsx";
import { ErrorBoundary } from "./ui/ErrorBoundary.jsx";
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
import AiSettings from "./pages/AiSettings.jsx";
import ContactGroups from "./pages/ContactGroups.jsx";
import WaCollections from "./pages/WaCollections.jsx";
import Reporting from "./pages/Reporting.jsx";
import Products from "./pages/Products.jsx";
import JoinLinks from "./pages/JoinLinks.jsx";
import StatusScheduler from "./pages/StatusScheduler.jsx";
import AiKeys from "./pages/AiKeys.jsx";
import PartnerInstances from "./pages/PartnerInstances.jsx";
import Content from "./pages/Content.jsx";
import ButtonAutoReplies from "./pages/ButtonAutoReplies.jsx";
import SendQueue from "./pages/SendQueue.jsx";
import Protection from "./pages/Protection.jsx";
import Calls from "./pages/Calls.jsx";
import Capabilities from "./pages/Capabilities.jsx";
import AdvertisingLinks from "./pages/AdvertisingLinks.jsx";
import Warmup from "./pages/Warmup.jsx";
import GroupMonitoring from "./pages/GroupMonitoring.jsx";
import TelegramAccounts from "./pages/TelegramAccounts.jsx";
import TeamCollaboration from "./pages/TeamCollaboration.jsx";
import Onboarding from "./pages/Onboarding.jsx";
import OwnNumbers from "./pages/OwnNumbers.jsx";
import ActiveContacts from "./pages/ActiveContacts.jsx";

export default function App() {
  return (
    <ErrorBoundary>
      <Toaster />
      <ConfirmHost />
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
        <Route path="ai-settings" element={<AiSettings />} />
        <Route path="contact-groups" element={<ContactGroups />} />
        <Route path="wa-collections" element={<WaCollections />} />
        <Route path="reporting" element={<Reporting />} />
        <Route path="products" element={<Products />} />
        <Route path="join-links" element={<JoinLinks />} />
        <Route path="status-scheduler" element={<StatusScheduler />} />
        <Route path="ai-keys" element={<AiKeys />} />
        <Route path="partner-instances" element={<PartnerInstances />} />
        <Route path="content" element={<Content />} />
        <Route path="button-auto-replies" element={<ButtonAutoReplies />} />
        <Route path="send-queue" element={<SendQueue />} />
        <Route path="protection" element={<Protection />} />
        <Route path="calls" element={<Calls />} />
        <Route path="capabilities" element={<Capabilities />} />
        <Route path="advertising-links" element={<AdvertisingLinks />} />
        <Route path="warmup" element={<Warmup />} />
        <Route path="team-collaboration" element={<TeamCollaboration />} />
        <Route path="onboarding" element={<Onboarding />} />
        <Route path="group-monitoring" element={<GroupMonitoring />} />
        <Route path="telegram-accounts" element={<TelegramAccounts />} />
        <Route path="own-numbers" element={<OwnNumbers />} />
        <Route path="active-contacts" element={<ActiveContacts />} />
        <Route path="*" element={<div className="text-slate-400">صفحه یافت نشد</div>} />
      </Route>
      </Routes>
    </ErrorBoundary>
  );
}
