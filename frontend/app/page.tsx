"use client";

import { useMemo, useState, type FormEvent } from "react";
import {
  createSubmission,
  queueSubmissionAnalysis,
} from "@/services/submission.service";

type View =
  | "Overview"
  | "Submissions"
  | "Brand library"
  | "Review queue"
  | "Insights"
  | "Submission details";
type Status =
  | "In review"
  | "Approved"
  | "Changes requested"
  | "Processing"
  | "Submitted"
  | "Draft";




type CampaignPurpose =
  | "general_marketing"
  | "social_media"
  | "influencer_promotion"
  | "newsletter"
  | "sponsorship_event";

type RequestedCheck =
  | "tone"
  | "terminology"
  | "messaging"
  | "factual_claim"
  | "visual"
  | "accessibility";

const campaignPurposeOptions: {
  value: CampaignPurpose;
  label: string;
}[] = [
  { value: "general_marketing", label: "General marketing" },
  { value: "social_media", label: "Social media" },
  { value: "influencer_promotion", label: "Influencer promotion" },
  { value: "newsletter", label: "Newsletter" },
  { value: "sponsorship_event", label: "Sponsorship / Event" },
];

const requestedCheckOptions: {
  value: RequestedCheck;
  label: string;
}[] = [
  { value: "tone", label: "Brand tone" },
  { value: "terminology", label: "Terminology" },
  { value: "messaging", label: "Messaging" },
  { value: "factual_claim", label: "Factual claims" },
  { value: "visual", label: "Visual consistency" },
  { value: "accessibility", label: "Accessibility" },
];

type Submission = {
  id: string;
  title: string;
  channel: string;
  owner: string;
  updated: string;
  status: Status;
  issues: number;
};

const navigation: { label: View; icon: string }[] = [
  { label: "Overview", icon: "◫" },
  { label: "Submissions", icon: "▤" },
  { label: "Brand library", icon: "▣" },
  { label: "Review queue", icon: "✓" },
  { label: "Insights", icon: "↗" },
];

const initialSubmissions: Submission[] = [
  {
    id: "BG-1048",
    title: "Summer campaign — social post",
    channel: "Social media",
    owner: "Aarav Sharma",
    updated: "12 min ago",
    status: "In review",
    issues: 3,
  },
  {
    id: "BG-1047",
    title: "Product launch announcement",
    channel: "Website",
    owner: "Priya Mehta",
    updated: "38 min ago",
    status: "Changes requested",
    issues: 2,
  },
  {
    id: "BG-1046",
    title: "Customer newsletter",
    channel: "Email",
    owner: "Rahul Verma",
    updated: "1 hour ago",
    status: "Approved",
    issues: 0,
  },
  {
    id: "BG-1045",
    title: "Brand awareness banner",
    channel: "Display ad",
    owner: "Ananya Rao",
    updated: "2 hours ago",
    status: "Processing",
    issues: 0,
  },
  {
    id: "BG-1044",
    title: "Influencer campaign copy",
    channel: "Campaign",
    owner: "Aarav Sharma",
    updated: "Yesterday",
    status: "Draft",
    issues: 0,
  },
];

const statusColors: Record<Status, string> = {
  "In review": "bg-violet-50 text-violet-700 ring-violet-200",
  Approved: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  "Changes requested": "bg-amber-50 text-amber-800 ring-amber-200",
  Processing: "bg-sky-50 text-sky-700 ring-sky-200",
  Submitted: "bg-blue-50 text-blue-700 ring-blue-200",
  Draft: "bg-slate-100 text-slate-600 ring-slate-200",
};

function StatusPill({ status }: { status: Status }) {
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${statusColors[status]}`}
    >
      <span className="mr-1.5" aria-hidden="true">
        {status === "Approved"
          ? "✓"
          : status === "Processing"
            ? "◷"
            : status === "Changes requested"
              ? "!"
              : status === "Draft"
                ? "○"
                : "●"}
      </span>
      {status}
    </span>
  );
}

function SubmissionTable({
  rows,
  onSelect,
}: {
  rows: Submission[];
  onSelect?: (submission: Submission) => void;
}) {
  if (rows.length === 0) {
    return (
      <div className="px-6 py-12 text-center">
        <p className="font-medium text-slate-700">
          No submissions found
        </p>
        <p className="mt-1 text-sm text-slate-500">
          Try changing your search or status filter.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-y border-slate-100 bg-slate-50/70 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-5 py-3 font-medium">Submission</th>
            <th className="px-5 py-3 font-medium">Owner</th>
            <th className="px-5 py-3 font-medium">Status</th>
            <th className="px-5 py-3 font-medium">Findings</th>
            <th className="px-5 py-3 font-medium">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((item) => (
            <tr
              key={item.id}
              className="transition hover:bg-violet-50/30"
            >
              <td className="px-5 py-4">
                {onSelect ? (
                  <button
                    type="button"
                    onClick={() => onSelect(item)}
                    className="text-left font-medium text-slate-800 hover:text-violet-700"
                  >
                    {item.title}
                  </button>
                ) : (
                  <p className="font-medium text-slate-800">
                    {item.title}
                  </p>
                )}
                <p className="mt-1 text-xs text-slate-500">
                  {item.id} · {item.channel}
                </p>
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                {item.owner}
              </td>
              <td className="px-5 py-4">
                <StatusPill status={item.status} />
              </td>
              <td className="px-5 py-4">
                <span
                  className={`font-medium ${
                    item.issues > 0
                      ? "text-amber-700"
                      : "text-slate-400"
                  }`}
                >
                  {item.status === "Processing"
                    ? "Pending"
                    : item.issues}
                </span>
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-slate-500">
                {item.updated}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Home() {
  const [activeView, setActiveView] = useState<View>("Overview");
  const [selectedSubmission, setSelectedSubmission] =
  useState<Submission | null>(null);
  const [submissions, setSubmissions] =
    useState<Submission[]>(initialSubmissions);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"All" | Status>("All");
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [draftText, setDraftText] = useState("");
  const [campaignPurpose, setCampaignPurpose] =
  useState<CampaignPurpose>("general_marketing");

const [requestedChecks, setRequestedChecks] =
  useState<RequestedCheck[]>([
    "tone",
    "terminology",
    "messaging",
    "factual_claim",
  ]);

function toggleRequestedCheck(check: RequestedCheck) {
  setRequestedChecks((current) =>
    current.includes(check)
      ? current.filter((item) => item !== check)
      : [...current, check]
  );
}
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
const [fileInputKey, setFileInputKey] = useState(0);
const [isSubmitting, setIsSubmitting] = useState(false);
const [formError, setFormError] = useState("");

const fileName = selectedFile?.name ?? "";
  const [notice, setNotice] = useState("");
  function handleOpenSubmission(submission: Submission) {
  setSelectedSubmission(submission);
  setActiveView("Submission details");
}
  const filteredSubmissions = useMemo(() => {
    return submissions.filter((item) => {
      const matchesSearch = [
        item.title,
        item.id,
        item.owner,
        item.channel,
      ].some((value) => value.toLowerCase().includes(search.toLowerCase()));

      const matchesStatus =
        statusFilter === "All" || item.status === statusFilter;

      const matchesView =
        activeView !== "Review queue" ||
        item.status === "In review" ||
        item.status === "Changes requested";

      return matchesSearch && matchesStatus && matchesView;
    });
  }, [submissions, search, statusFilter, activeView]);

  async function handleSubmission(
  event: FormEvent<HTMLFormElement>
) {
  event.preventDefault();
  setFormError("");
  setNotice("");

  if (!title.trim()) {
    setFormError("Submission title is required.");
    return;
  }

  const hasText = Boolean(draftText.trim());
  const hasFile = selectedFile !== null;

  if (hasText === hasFile) {
    setFormError(
      "Please provide either pasted text or one file, not both."
    );
    return;
  }

  setIsSubmitting(true);

  try {
    const created = await createSubmission(
      selectedFile
        ? {
            title: title.trim(),
            file: selectedFile,
          }
        : {
            title: title.trim(),
            text: draftText.trim(),
          }
    );

    const newSubmission: Submission = {
      id: created.submission_id,
      title: title.trim(),
      channel: hasFile ? "File upload" : "Text",
      owner: "You",
      updated: "Just now",
      status: "Submitted",
      issues: 0,
    };

    setSubmissions((current) => [
      newSubmission,
      ...current,
    ]);

    setSearch("");
    setStatusFilter("All");
    setActiveView("Submissions");

    setTitle("");
    setDraftText("");
    setSelectedFile(null);
    setFileInputKey((key) => key + 1);

    setShowCreate(false);

    try {
      const queued = await queueSubmissionAnalysis(
        created.submission_id,
        created.version_number
      );

      setSubmissions((current) =>
        current.map((item) =>
          item.id === created.submission_id
            ? { ...item, status: "Processing" }
            : item
        )
      );

      setNotice(
        `Analysis queued successfully. Job ID: ${queued.job_id}`
      );
    } catch (error) {
      setNotice(
        `Submission created, but analysis could not be queued: ${
          error instanceof Error
            ? error.message
            : "Unknown error"
        }`
      );
    }
  } catch (error) {
    setFormError(
      error instanceof Error
        ? error.message
        : "Unable to submit content. Please try again."
    );
  } finally {
    setIsSubmitting(false);
  }
}

  const pageInfo: Record<View, { subtitle: string }> = {
    Overview: {
      subtitle:
        "Your workspace at a glance. Review content and keep your brand consistent.",
    },
    Submissions: {
      subtitle:
        "Find submissions, track their status and open the latest activity.",
    },
    "Brand library": {
      subtitle:
        "The reference library for guidelines, terminology and approved facts.",
    },
    "Review queue": {
      subtitle:
        "Illustrative review queue for content that needs human attention.",
    },
    Insights: {
      subtitle:
        "A preview of governance trends and recurring issues.",
    },
    "Submission details": {
  subtitle: "Review submission information and analysis findings.",
},
  };

  return (
    <main className="min-h-screen bg-[#f7f7fb] text-slate-800">
      <div className="grid min-h-screen lg:grid-cols-[244px_minmax(0,1fr)]">
        <aside className="border-b border-slate-200 bg-white px-4 py-5 lg:border-b-0 lg:border-r lg:px-4">
          <div className="flex items-center gap-3 px-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600 text-xl font-semibold text-white shadow-sm shadow-violet-200">
              i
            </div>
            <div>
              <p className="text-lg font-semibold tracking-tight text-slate-900">
                BrandGuard<span className="text-violet-600"> AI</span>
                
              </p>
              <p className="text-xs text-slate-500">Brand Governance</p>
            </div>
          </div>

          <div className="mt-8 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
              Workspace
            </p>
            <div className="mt-2 flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-100 text-sm font-semibold text-amber-800">
                B
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-800">
                  Brand Studio
                </p>
                <p className="text-xs text-slate-500">Demo workspace</p>
              </div>
              <span className="text-slate-400" aria-hidden="true">
               ⌄
              </span>
            </div>
          </div>

          <nav className="mt-7" aria-label="Main navigation">
            <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Workspace
            </p>
            <div className="grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-1">
              {navigation.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => {
                    setActiveView(item.label);
                    setSearch("");
                    setStatusFilter("All");
                    setNotice("");
                  }}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                    activeView === item.label
                      ? "bg-violet-50 font-semibold text-violet-700"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <span className="w-5 text-center text-base" aria-hidden="true">
                    {item.icon}
                  </span>
                  {item.label}
                  {item.label === "Review queue" && (
                    <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                      {submissions.filter(
                        (item) =>
                          item.status === "In review" ||
                          item.status === "Changes requested",
                      ).length}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </nav>

          <div className="mt-7 hidden rounded-xl border border-violet-100 bg-gradient-to-br from-violet-50 to-indigo-50 p-4 lg:block">
            <span className="text-xl" aria-hidden="true">
              ✦
            </span>
            <p className="mt-2 text-sm font-semibold text-slate-800">
              Keep every message on-brand
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-600">
              Check content against your organisation&apos;s approved references.
            </p>
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="mt-3 text-xs font-semibold text-violet-700 hover:text-violet-900"
            >
              Start an analysis →
            </button>
          </div>

          <div className="mt-7 hidden border-t border-slate-100 pt-4 lg:block">
            <div className="flex items-center gap-3 px-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-200 text-sm font-semibold text-slate-700">
                T
              </div>
              <div>
                <p className="text-sm font-medium text-slate-800">Frontend demo</p>
                <p className="text-xs text-slate-500">Prototype workspace</p>
              </div>
            </div>
          </div>
        </aside>

        <section className="min-w-0">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-4 sm:px-8">
            <div>
              <p className="text-xs text-slate-400">
                Brand Studio <span className="mx-1">/</span> {activeView}
              </p>
              <h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">
                {activeView}
              </h1>
            </div>

            <div className="flex items-center gap-3">
              <span className="hidden rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 sm:inline-flex">
                Demo mode · Backend not connected
              </span>
              <button
                type="button"
                onClick={() => setShowCreate(true)}
                className="rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2"
              >
                <span className="mr-1.5" aria-hidden="true">
                  +
                </span>
                New analysis
              </button>
            </div>
          </header>

          <div className="mx-auto max-w-[1500px] space-y-6 p-5 sm:p-8">
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <span aria-hidden="true">ⓘ</span>
              <p>
                <strong>Prototype preview.</strong> All listed submissions and metrics are illustrative. Analysis, login and approvals are not connected to the backend yet.
              </p>
            </div>

            {notice && (
              <div
                role="status"
                className="flex items-start justify-between gap-3 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-900"
              >
                <p>{notice}</p>
                <button
                  type="button"
                  onClick={() => setNotice("")}
                  aria-label="Dismiss message"
                  className="font-semibold"
                >
                  ×
                </button>
              </div>
            )}

            <div>
              <p className="text-sm leading-6 text-slate-500">
                {pageInfo[activeView].subtitle}
              </p>
            </div>

            {activeView === "Overview" && (
              <>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    {
                      label: "Total submissions",
                      value: submissions.length.toString(),
                      note: "Illustrative records",
                      icon: "▤",
                      tone: "bg-violet-50 text-violet-700",
                    },
                    {
                      label: "Awaiting review",
                      value: submissions
                        .filter(
                          (item) =>
                            item.status === "In review" ||
                            item.status === "Changes requested",
                        )
                        .length.toString(),
                      note: "Needs human attention",
                      icon: "◷",
                      tone: "bg-amber-50 text-amber-700",
                    },
                    {
                      label: "Approved",
                      value: submissions
                        .filter((item) => item.status === "Approved")
                        .length.toString(),
                      note: "Demo status only",
                      icon: "✓",
                      tone: "bg-emerald-50 text-emerald-700",
                    },
                    {
                      label: "Processing",
                      value: submissions
                        .filter((item) => item.status === "Processing")
                        .length.toString(),
                      note: "Not a live job status",
                      icon: "✧",
                      tone: "bg-sky-50 text-sky-700",
                    },
                  ].map((card) => (
                    <div
                      key={card.label}
                      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-100/60"
                    >
                      <div className="flex items-start justify-between">
                        <p className="text-sm font-medium text-slate-500">
                          {card.label}
                        </p>
                        <span
                          className={`flex h-9 w-9 items-center justify-center rounded-lg text-lg ${card.tone}`}
                          aria-hidden="true"
                        >
                          {card.icon}
                        </span>
                      </div>
                      <p className="mt-4 text-3xl font-semibold tracking-tight text-slate-900">
                        {card.value}
                      </p>
                      <p className="mt-2 text-xs text-slate-500">{card.note}</p>
                    </div>
                  ))}
                </div>

                <div className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(270px,0.8fr)]">
                  <section className="min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm shadow-slate-100/60">
                    <div className="flex flex-wrap items-center justify-between gap-3 p-5">
                      <div>
                        <h2 className="font-semibold text-slate-900">
                          Recent submissions
                        </h2>
                        <p className="mt-1 text-xs text-slate-500">
                          Illustrative activity for the prototype
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setActiveView("Submissions")}
                        className="text-sm font-semibold text-violet-700 hover:text-violet-900"
                      >
                        View all →
                      </button>
                    </div>
                    <SubmissionTable rows={submissions.slice(0, 4)}
                    onSelect={handleOpenSubmission} />
                  </section>

                  <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-100/60">
                    <div className="flex items-center justify-between">
                      <h2 className="font-semibold text-slate-900">
                        Quick actions
                      </h2>
                      <span className="text-lg text-violet-600" aria-hidden="true">
                        ✦
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-slate-500">
                      Explore the main prototype workflows.
                    </p>

                    <div className="mt-5 space-y-3">
                      <button
                        type="button"
                        onClick={() => setShowCreate(true)}
                        className="flex w-full items-center gap-3 rounded-xl border border-slate-200 p-3 text-left transition hover:border-violet-300 hover:bg-violet-50/50"
                      >
                        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-violet-100 text-lg text-violet-700">
                          +
                        </span>
                        <span>
                          <span className="block text-sm font-semibold text-slate-800">
                            Submit content
                          </span>
                          <span className="mt-1 block text-xs text-slate-500">
                            Enter text or select a file
                          </span>
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveView("Review queue")}
                        className="flex w-full items-center gap-3 rounded-xl border border-slate-200 p-3 text-left transition hover:border-violet-300 hover:bg-violet-50/50"
                      >
                        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-100 text-lg text-amber-800">
                          ✓
                        </span>
                        <span>
                          <span className="block text-sm font-semibold text-slate-800">
                            Review queue
                          </span>
                          <span className="mt-1 block text-xs text-slate-500">
                            Inspect pending demo items
                          </span>
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveView("Brand library")}
                        className="flex w-full items-center gap-3 rounded-xl border border-slate-200 p-3 text-left transition hover:border-violet-300 hover:bg-violet-50/50"
                      >
                        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-100 text-lg text-emerald-700">
                          ▣
                        </span>
                        <span>
                          <span className="block text-sm font-semibold text-slate-800">
                            Brand library
                          </span>
                          <span className="mt-1 block text-xs text-slate-500">
                            Explore sample reference cards
                          </span>
                        </span>
                      </button>
                    </div>

                    <div className="mt-5 rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">
                      Suggested corrections and approval decisions must be returned and recorded by the backend in the integrated version.
                    </div>
                  </section>
                </div>
              </>
            )}

            {activeView === "Submissions" && (
              <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm shadow-slate-100/60">
                <div className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
                  <div>
                    <h2 className="font-semibold text-slate-900">
                      All submissions
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      {filteredSubmissions.length} demo record(s)
                    </p>
                  </div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <input
                      aria-label="Search submissions"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search submissions..."
                      className="min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100 sm:w-56"
                    />
                    <select
                      aria-label="Filter by status"
                      value={statusFilter}
                      onChange={(event) =>
                        setStatusFilter(event.target.value as "All" | Status)
                      }
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-violet-400"
                    >
                      <option value="All">All statuses</option>
                      <option value="Draft">Draft</option>
                      <option value="Processing">Processing</option>
                      <option value="In review">In review</option>
                      <option value="Changes requested">Changes requested</option>
                      <option value="Approved">Approved</option>
                    </select>
                  </div>
                </div>
                <SubmissionTable rows={filteredSubmissions}
                onSelect={handleOpenSubmission}
                 />
              </section>
            )}

            {activeView === "Review queue" && (
              <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="p-5">
                  <h2 className="font-semibold text-slate-900">
                    Items awaiting human attention
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    This sample queue demonstrates the proposed review interface; it does not perform real approval actions.
                  </p>
                </div>
                <SubmissionTable rows={filteredSubmissions}
                 onSelect={handleOpenSubmission}
                />
                <div className="border-t border-slate-100 bg-slate-50 px-5 py-4 text-xs leading-5 text-slate-600">
                  In the integrated workflow, reviewer comments, request-changes actions and final decisions will be submitted to FastAPI. Only the backend can confirm approval.
                </div>
              </section>
            )}

            {activeView === "Brand library" && (
              <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {[
                  {
                    icon: "✦",
                    title: "Brand voice guidelines",
                    category: "Guidelines",
                    detail: "Tone, messaging principles and communication standards.",
                    status: "Sample reference",
                  },
                  {
                    icon: "Aa",
                    title: "Approved terminology",
                    category: "Terminology",
                    detail: "Preferred terms and language that should be avoided.",
                    status: "Sample reference",
                  },
                  {
                    icon: "✓",
                    title: "Verified facts and claims",
                    category: "Facts & claims",
                    detail: "Approved claims and their supporting evidence references.",
                    status: "Sample reference",
                  },
                ].map((card) => (
                  <article
                    key={card.title}
                    className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-100/60"
                  >
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-50 font-semibold text-violet-700">
                      {card.icon}
                    </div>
                    <p className="mt-4 text-xs font-medium uppercase tracking-wider text-violet-700">
                      {card.category}
                    </p>
                    <h2 className="mt-2 font-semibold text-slate-900">
                      {card.title}
                    </h2>
                    <p className="mt-2 min-h-12 text-sm leading-6 text-slate-500">
                      {card.detail}
                    </p>
                    <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
                      {card.status} · Not connected to stored brand data
                    </div>
                  </article>
                ))}
              </section>
            )}

            {activeView === "Insights" && (
              <div className="grid gap-5 lg:grid-cols-2">
                <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h2 className="font-semibold text-slate-900">
                    Governance overview
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Example workflow distribution, calculated from the sample records.
                  </p>
                  <div className="mt-6 space-y-5">
                    {(
                      [
                        ["Approved", "bg-emerald-500"],
                        ["In review", "bg-violet-500"],
                        ["Changes requested", "bg-amber-500"],
                        ["Processing", "bg-sky-500"],
                        ["Draft", "bg-slate-400"],
                      ] as [Status, string][]
                    ).map(([status, color]) => {
                      const count = submissions.filter(
                        (item) => item.status === status,
                      ).length;
                      const percent = submissions.length
                        ? (count / submissions.length) * 100
                        : 0;
                      return (
                        <div key={status}>
                          <div className="mb-2 flex justify-between text-sm">
                            <span className="text-slate-600">{status}</span>
                            <span className="font-medium text-slate-800">
                              {count}
                            </span>
                          </div>
                          <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                            <div
                              className={`h-full rounded-full ${color}`}
                              style={{ width: `${percent}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>

                <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h2 className="font-semibold text-slate-900">
                    Recurring issue categories
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Example categories for the future analytics view.
                  </p>
                  <div className="mt-5 space-y-3">
                    {[
                      ["Terminology consistency", "Preferred terms and wording"],
                      ["Brand voice", "Tone and communication style"],
                      ["Claims and evidence", "Approved facts and substantiation"],
                      ["Visual consistency", "Logo, colour and accessibility"],
                    ].map(([name, detail]) => (
                      <div
                        key={name}
                        className="rounded-lg border border-slate-100 p-4"
                      >
                        <p className="text-sm font-medium text-slate-800">
                          {name}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">{detail}</p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-4 text-xs leading-5 text-slate-500">
                    No AI findings are generated by this demo. Production analytics will display persisted backend results.
                  </p>
                </section>
              </div>
            )}
            {activeView === "Submission details" && (
  <section className="space-y-5">
    <button
      type="button"
      onClick={() => setActiveView("Submissions")}
      className="text-sm font-semibold text-violet-700 hover:text-violet-900"
    >
      ← Back to submissions
    </button>

    {selectedSubmission ? (
      <>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs text-slate-500">
                {selectedSubmission.id}
              </p>
              <h2 className="mt-1 text-xl font-semibold text-slate-900">
                {selectedSubmission.title}
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                {selectedSubmission.channel} · {selectedSubmission.owner}
              </p>
            </div>

            <StatusPill status={selectedSubmission.status} />
          </div>

          <div className="mt-5 border-t border-slate-100 pt-4">
            <p className="text-sm font-medium text-slate-700">
              Findings summary
            </p>
            <p className="mt-1 text-sm text-slate-500">
              {selectedSubmission.issues} issue(s) recorded in this sample.
            </p>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Analysis findings
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Illustrative examples showing how brand issues will be presented.
            These are not actual AI analysis results.
          </p>
        </div>

        {[
          {
            category: "Brand voice",
            severity: "Medium",
            affected: "Get amazing results instantly!",
            explanation:
              "This wording may sound overly promotional and may not match the approved brand tone.",
            guideline: "Follow the approved tone of voice guidelines.",
            suggestion:
              "Explore how this product can support your everyday needs.",
          },
          {
            category: "Terminology",
            severity: "High",
            affected: "Guaranteed results",
            explanation:
              "A guaranteed claim should not be used unless it is supported by approved brand information.",
            guideline: "Use only approved terminology and verified claims.",
            suggestion:
              "Replace with a factual, approved product description.",
          },
          {
            category: "Facts and claims",
            severity: "High",
            affected: "Unverified product performance claim",
            explanation:
              "The claim needs supporting evidence from an approved reference.",
            guideline: "Verify factual claims against approved brand references.",
            suggestion:
              "Add a verified source or remove the unsupported claim.",
          },
        ].map((finding) => (
          <article
            key={finding.category}
            className="rounded-xl border border-slate-200 bg-white p-5"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold text-slate-900">
                {finding.category}
              </h3>
              <span
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  finding.severity === "High"
                    ? "bg-red-50 text-red-700"
                    : "bg-amber-50 text-amber-700"
                }`}
              >
                {finding.severity} severity
              </span>
            </div>

            <div className="mt-4 space-y-3 text-sm">
              <div>
                <p className="font-medium text-slate-700">Affected content</p>
                <p className="mt-1 text-slate-600">{finding.affected}</p>
              </div>

              <div>
                <p className="font-medium text-slate-700">Explanation</p>
                <p className="mt-1 text-slate-600">{finding.explanation}</p>
              </div>

              <div>
                <p className="font-medium text-slate-700">Brand guideline</p>
                <p className="mt-1 text-slate-600">{finding.guideline}</p>
              </div>

              <div className="rounded-lg bg-violet-50 p-3">
                <p className="font-medium text-violet-900">
                  Suggested correction
                </p>
                <p className="mt-1 text-violet-800">
                  {finding.suggestion}
                </p>
              </div>
            </div>
          </article>
        ))}
      </>
    ) : (
      <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
        No submission selected. Return to submissions and choose an item.
      </p>
    )}
  </section>
)}
            <footer className="border-t border-slate-200 pt-4 text-xs leading-5 text-slate-400">
              BrandGuard AI · Frontend prototype · Demo records are illustrative and do not represent live backend data.
            </footer>
          </div>
        </section>
      </div>

      {showCreate && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/45 p-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowCreate(false);
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-analysis-title"
            className="my-6 w-full max-w-xl rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between border-b border-slate-100 p-6">
              <div>
                <h2
                  id="new-analysis-title"
                  className="text-lg font-semibold text-slate-900"
                >
                  New content submission
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Enter content or choose a supported file.
                </p>
              </div>
              <button
                type="button"
                aria-label="Close dialog"
                onClick={() => setShowCreate(false)}
                className="rounded-lg px-2 py-1 text-xl text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                ×
              </button>
            </div>

            <form onSubmit={handleSubmission} className="space-y-5 p-6">
              <div>
                <label
                  htmlFor="submission-title"
                  className="mb-2 block text-sm font-medium text-slate-700"
                >
                  Submission title
                </label>
                <input
                  id="submission-title"
                  required
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="e.g. Summer campaign social post"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />
              </div>

              <div>
                <div>
  <label
    htmlFor="campaign-purpose"
    className="mb-2 block text-sm font-medium text-slate-700"
  >
    Campaign purpose
  </label>

  <select
    id="campaign-purpose"
    value={campaignPurpose}
    onChange={(event) =>
      setCampaignPurpose(event.target.value as CampaignPurpose)
    }
    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
  >
    {campaignPurposeOptions.map((option) => (
      <option key={option.value} value={option.value}>
        {option.label}
      </option>
    ))}
  </select>
</div>

<div>
  <p className="mb-2 text-sm font-medium text-slate-700">
    Requested brand checks
  </p>

  <div className="grid gap-3 sm:grid-cols-2">
    {requestedCheckOptions.map((check) => (
      <label
        key={check.value}
        className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 p-3 text-sm text-slate-700 hover:bg-violet-50"
      >
        <input
          type="checkbox"
          checked={requestedChecks.includes(check.value)}
          onChange={() => toggleRequestedCheck(check.value)}
          className="h-4 w-4 accent-violet-600"
        />
        {check.label}
      </label>
    ))}
  </div>

  <p className="mt-2 text-xs text-slate-500">
    Select the brand checks relevant to your content.
  </p>
</div>
                <label
                  htmlFor="submission-content"
                  className="mb-2 block text-sm font-medium text-slate-700"
                >
                  Content to review
                </label>
                <textarea
                  id="submission-content"
                  value={draftText}
                  onChange={(event) => setDraftText(event.target.value)}
                  rows={5}
                  placeholder="Paste your marketing copy here..."
                  className="w-full resize-y rounded-lg border border-slate-200 px-3 py-3 text-sm outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />
              </div>

              <div>
                <label
                  htmlFor="submission-file"
                  className="mb-2 block text-sm font-medium text-slate-700"
                >
                  Or choose a file
                </label>
                <input
                key={fileInputKey}
                  id="submission-file"
                  type="file"
                  accept=".txt,.pdf,.docx,.png,.jpg,.jpeg"
                  onChange={(event) => {
  const file = event.target.files?.[0] ?? null;

  setFormError("");

  if (!file) {
    setSelectedFile(null);
    return;
  }

  const extension = file.name.split(".").pop()?.toLowerCase();

  const allowedExtensions = [
    "txt",
    "pdf",
    "docx",
    "png",
    "jpg",
    "jpeg",
  ];

  if (!extension || !allowedExtensions.includes(extension)) {
    setSelectedFile(null);
    setFileInputKey((key) => key + 1);
    setFormError(
      "Unsupported file format. Please select TXT, PDF, DOCX, PNG, JPG or JPEG."
    );
    return;
  }

  setSelectedFile(file);
}}
                  className="block w-full rounded-lg border border-slate-200 p-2 text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-violet-50 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-violet-700"
                />
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Supported formats: TXT, PDF, DOCX, PNG, JPG and JPEG.
                  Select either pasted text or a file.
                </p>
                {fileName && (
                  <p className="mt-2 text-xs font-medium text-violet-700">
                    Selected: {fileName}
                  </p>
                )}
              </div>

              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-900">
                Only the title and selected content source are sent to the current API. Campaign purpose and requested checks are prototype selections and are not yet included in the backend contract.
              </div>
              {formError && (
  <p
    role="alert"
    className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
  >
    {formError}
  </p>
)}
              <div className="flex flex-wrap justify-end gap-3 border-t border-slate-100 pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2"
                >
                  {isSubmitting ? "Submitting..." : "Submit for analysis"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}