"use client";

import { useMemo, useState, type FormEvent } from "react";

type View =
  | "Overview"
  | "Submissions"
  | "Brand library"
  | "Review queue"
  | "Insights";

type Status =
  | "In review"
  | "Approved"
  | "Changes requested"
  | "Processing"
  | "Draft";

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

function SubmissionTable({ rows }: { rows: Submission[] }) {
  if (rows.length === 0) {
    return (
      <div className="px-6 py-12 text-center">
        <p className="font-medium text-slate-700">No submissions found</p>
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
                <p className="font-medium text-slate-800">{item.title}</p>
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
                    item.issues > 0 ? "text-amber-700" : "text-slate-400"
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
  const [submissions, setSubmissions] =
    useState<Submission[]>(initialSubmissions);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"All" | Status>("All");
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [draftText, setDraftText] = useState("");
  const [fileName, setFileName] = useState("");
  const [notice, setNotice] = useState("");

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

  function createDemoSubmission(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!draftText.trim() && !fileName) {
      setNotice("Please enter some content or select a supported file.");
      return;
    }

    const newSubmission: Submission = {
      id: `DEMO-${Date.now().toString().slice(-5)}`,
      title: title.trim(),
      channel: fileName ? "File upload" : "Text",
      owner: "You",
      updated: "Just now",
      status: "Draft",
      issues: 0,
    };

    setSubmissions((current) => [newSubmission, ...current]);
    setSearch("");
    setStatusFilter("All");
    setActiveView("Submissions");
    setTitle("");
    setDraftText("");
    setFileName("");
    setShowCreate(false);
    setNotice(
      "Demo only: the item was added locally. It has not been sent to FastAPI or analysed.",
    );
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
                    <SubmissionTable rows={submissions.slice(0, 4)} />
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
                <SubmissionTable rows={filteredSubmissions} />
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
                <SubmissionTable rows={filteredSubmissions} />
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

            <form onSubmit={createDemoSubmission} className="space-y-5 p-6">
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
                  id="submission-file"
                  type="file"
                  accept=".txt,.pdf,.docx,.png,.jpg,.jpeg"
                  onChange={(event) =>
                    setFileName(event.target.files?.[0]?.name ?? "")
                  }
                  className="block w-full rounded-lg border border-slate-200 p-2 text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-violet-50 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-violet-700"
                />
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Supported prototype formats: TXT, PDF, DOCX, PNG, JPG/JPEG. The selected file is not uploaded in demo mode.
                </p>
                {fileName && (
                  <p className="mt-2 text-xs font-medium text-violet-700">
                    Selected: {fileName}
                  </p>
                )}
              </div>

              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-900">
                Demo mode: this form adds a draft to the current browser session only. It does not send content to FastAPI or run an analysis.
              </div>

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
                  className="rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2"
                >
                  Add demo submission
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}