"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";

import {
  createSubmission,
  queueSubmissionAnalysis,
} from "@/services/submission.service";

import { getAnalysisJob } from "@/services/analysis.service";

import {
  extractFindings,
  getSubmissionFindings,
} from "@/services/findings.service";

import type {
  AnalysisJobStatus,
  Finding,
} from "@/types/api-contracts";

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
  | "Draft"
  | "Failed";

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
  | "factual_claim";

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
  ];

type Submission = {
  id: string;
  title: string;
  channel: string;
  owner: string;
  updated: string;
  status: Status;
  issues: number;
  versionNumber?: number;
  jobId?: string;
  jobStatus?: AnalysisJobStatus;
  findings?: Finding[];
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
    owner: "Demo user",
    updated: "Sample record",
    status: "In review",
    issues: 3,
  },
  {
    id: "BG-1047",
    title: "Product launch announcement",
    channel: "Website",
    owner: "Demo user",
    updated: "Sample record",
    status: "Changes requested",
    issues: 2,
  },
  {
    id: "BG-1046",
    title: "Customer newsletter",
    channel: "Email",
    owner: "Demo user",
    updated: "Sample record",
    status: "Approved",
    issues: 0,
  },
];

const statusColors: Record<Status, string> = {
  "In review": "bg-violet-50 text-violet-700 ring-violet-200",
  Approved: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  "Changes requested":
    "bg-amber-50 text-amber-800 ring-amber-200",
  Processing: "bg-sky-50 text-sky-700 ring-sky-200",
  Submitted: "bg-blue-50 text-blue-700 ring-blue-200",
  Draft: "bg-slate-100 text-slate-600 ring-slate-200",
  Failed: "bg-red-50 text-red-700 ring-red-200",
};

const severityColors: Record<string, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-blue-50 text-blue-700",
  info: "bg-slate-100 text-slate-700",
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
            : status === "Failed"
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
  onSelect: (submission: Submission) => void;
}) {
  if (rows.length === 0) {
    return (
      <div className="px-6 py-12 text-center">
        <p className="font-medium text-slate-700">
          No submissions found
        </p>
        <p className="mt-1 text-sm text-slate-500">
          Change your search or create a new text submission.
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
            <tr key={item.id} className="transition hover:bg-violet-50/30">
              <td className="px-5 py-4">
                <button
                  type="button"
                  onClick={() => onSelect(item)}
                  className="text-left font-medium text-slate-800 hover:text-violet-700"
                >
                  {item.title}
                </button>

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
                  className={
                    item.issues > 0
                      ? "font-medium text-amber-700"
                      : "text-slate-400"
                  }
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

  const [selectedSubmissionId, setSelectedSubmissionId] =
    useState<string | null>(null);

  const [submissions, setSubmissions] =
    useState<Submission[]>(initialSubmissions);

  const submissionsRef = useRef(submissions);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] =
    useState<"All" | Status>("All");

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

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  function toggleRequestedCheck(check: RequestedCheck) {
    setRequestedChecks((current) =>
      current.includes(check)
        ? current.filter((item) => item !== check)
        : [...current, check],
    );
  }

  const [notice, setNotice] = useState("");

  const selectedSubmission = submissions.find(
    (item) => item.id === selectedSubmissionId,
  ) ?? null;

  useEffect(() => {
    submissionsRef.current = submissions;
  }, [submissions]);

  const filteredSubmissions = useMemo(() => {
    return submissions.filter((item) => {
      const matchesSearch = [
        item.title,
        item.id,
        item.owner,
        item.channel,
      ].some((value) =>
        value.toLowerCase().includes(search.toLowerCase()),
      );

      const matchesStatus =
        statusFilter === "All" || item.status === statusFilter;

      const matchesView =
        activeView !== "Review queue" ||
        item.status === "In review" ||
        item.status === "Changes requested";

      return matchesSearch && matchesStatus && matchesView;
    });
  }, [submissions, search, statusFilter, activeView]);

  // Poll only jobs created through the live backend flow.
  useEffect(() => {
    let stopped = false;
    let polling = false;

    async function pollActiveJobs() {
      if (polling || stopped) return;

      polling = true;

      try {
        const activeJobs = submissionsRef.current.filter(
          (item) =>
            item.jobId &&
            (item.jobStatus === "queued" ||
              item.jobStatus === "processing"),
        );

        for (const item of activeJobs) {
          if (stopped || !item.jobId) break;

          try {
            const job = await getAnalysisJob(item.jobId);

            let findings: Finding[] | undefined;

            if (
              job.status === "completed" ||
              job.status === "partial"
            ) {
              const response = await getSubmissionFindings(
                item.id,
                item.versionNumber ?? 1,
              );

              findings = extractFindings(response);
            }

            if (stopped) break;

            const nextStatus: Status =
              job.status === "failed"
                ? "Failed"
                : job.status === "completed" ||
                  job.status === "partial"
                  ? "In review"
                  : "Processing";

            setSubmissions((current) =>
              current.map((row) =>
                row.id !== item.id
                  ? row
                  : {
                    ...row,
                    status: nextStatus,
                    jobStatus: job.status,
                    ...(findings !== undefined
                      ? {
                        findings,
                        issues: findings.length,
                      }
                      : {}),
                  },
              ),
            );
          } catch (error) {
            // Keep the job active and retry on the next poll.
            console.error(
              `Could not refresh analysis for ${item.id}`,
              error,
            );
          }
        }
      } finally {
        polling = false;
      }
    }

    void pollActiveJobs();

    const timer = window.setInterval(() => {
      void pollActiveJobs();
    }, 2500);

    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  function handleOpenSubmission(submission: Submission) {
    setSelectedSubmissionId(submission.id);
    setActiveView("Submission details");
    setNotice("");
  }

  async function handleSubmission(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    setFormError("");
    setNotice("");

    if (!title.trim()) {
      setFormError("Submission title is required.");
      return;
    }

    if (!draftText.trim()) {
      setFormError("Paste the text you want BrandGuard AI to review.");
      return;
    }

    setIsSubmitting(true);

    let createdId: string | null = null;

    try {
      const created = await createSubmission({
        title: title.trim(),
        text: draftText.trim(),
      });

      createdId = created.submission_id;

      const newSubmission: Submission = {
        id: created.submission_id,
        title: title.trim(),
        channel: "Text",
        owner: "You",
        updated: "Just now",
        status: "Submitted",
        issues: 0,
        versionNumber: created.version_number,
      };

      setSubmissions((current) => [
        newSubmission,
        ...current,
      ]);

      setSearch("");
      setStatusFilter("All");
      setSelectedSubmissionId(created.submission_id);
      setActiveView("Submission details");
      setTitle("");
      setDraftText("");
      setCampaignPurpose("general_marketing");
      setRequestedChecks([
        "tone",
        "terminology",
        "messaging",
        "factual_claim",
      ]);
      setShowCreate(false);

      try {
        const queued = await queueSubmissionAnalysis(
          created.submission_id,
          created.version_number,
        );

        setSubmissions((current) =>
          current.map((item) =>
            item.id !== created.submission_id
              ? item
              : {
                ...item,
                status:
                  queued.status === "failed"
                    ? "Failed"
                    : queued.status === "completed" ||
                      queued.status === "partial"
                      ? "In review"
                      : "Processing",
                jobId: queued.job_id,
                versionNumber: queued.version_number,
                jobStatus: queued.status,
              },
          ),
        );

        setNotice(
          `Submission saved. Analysis job: ${queued.status}.`,
        );
      } catch (error) {
        setNotice(
          `Your submission was saved, but analysis could not be queued. ${error instanceof Error
            ? error.message
            : "Please retry the analysis request."
          }`,
        );
      }
    } catch (error) {
      setFormError(
        error instanceof Error
          ? error.message
          : "Unable to submit content. Please try again.",
      );

      if (createdId) {
        setSelectedSubmissionId(createdId);
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  const pageInfo: Record<View, string> = {
    Overview:
      "Your workspace at a glance. Review content and keep your brand consistent.",
    Submissions:
      "View submissions, track analysis status and open individual reports.",
    "Brand library":
      "Approved guidelines, terminology and facts will be managed here.",
    "Review queue":
      "Content awaiting human review. Final decisions remain with authorised reviewers.",
    Insights:
      "An overview of submission status and the findings generated by analysis.",
    "Submission details":
      "Inspect analysis status and persisted findings for the selected submission.",
  };

  const liveSubmissions = submissions.filter((item) => item.jobId);

  const processingCount = liveSubmissions.filter(
    (item) =>
      item.jobStatus === "queued" ||
      item.jobStatus === "processing",
  ).length;

  const liveFindingCount = liveSubmissions.reduce(
    (total, item) => total + (item.findings?.length ?? 0),
    0,
  );

  return (
    <main className="min-h-screen bg-[#f7f7fb] text-slate-800">
      <div className="grid min-h-screen lg:grid-cols-[244px_minmax(0,1fr)]">
        <aside className="border-b border-slate-200 bg-white px-4 py-5 lg:border-b-0 lg:border-r lg:px-4">
          <div className="flex items-center gap-3 px-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600 text-xl font-semibold text-white">
              B
            </div>

            <div>
              <p className="text-lg font-semibold tracking-tight text-slate-900">
                BrandGuard<span className="text-violet-600"> AI</span>
              </p>
              <p className="text-xs text-slate-500">
                Brand Governance
              </p>
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
                  Active organisation
                </p>
                <p className="text-xs text-slate-500">
                  Connected API
                </p>
              </div>
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
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${activeView === item.label
                    ? "bg-violet-50 font-semibold text-violet-700"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                    }`}
                >
                  <span
                    className="w-5 text-center text-base"
                    aria-hidden="true"
                  >
                    {item.icon}
                  </span>

                  {item.label}

                  {item.label === "Review queue" && (
                    <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                      {
                        submissions.filter(
                          (item) =>
                            item.status === "In review" ||
                            item.status === "Changes requested",
                        ).length
                      }
                    </span>
                  )}
                </button>
              ))}
            </div>
          </nav>

          <div className="mt-7 hidden rounded-xl border border-violet-100 bg-violet-50 p-4 lg:block">
            <span className="text-xl" aria-hidden="true">
              ✦
            </span>

            <p className="mt-2 text-sm font-semibold text-slate-800">
              Keep every message on-brand
            </p>

            <p className="mt-1 text-xs leading-5 text-slate-600">
              Submit text and review the findings returned by the analysis worker.
            </p>

            <button
              type="button"
              onClick={() => {
                setFormError("");
                setShowCreate(true);
              }}
              className="mt-3 text-xs font-semibold text-violet-700 hover:text-violet-900"
            >
              Start an analysis →
            </button>
          </div>
        </aside>

        <section className="min-w-0">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-4 sm:px-8">
            <div>
              <p className="text-xs text-slate-400">
                BrandGuard AI <span className="mx-1">/</span> {activeView}
              </p>

              <h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">
                {activeView}
              </h1>
            </div>

            <button
              type="button"
              onClick={() => {
                setFormError("");
                setShowCreate(true);
              }}
              className="rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2"
            >
              + New analysis
            </button>
          </header>

          <div className="mx-auto max-w-[1500px] space-y-6 p-5 sm:p-8">
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
              <strong>Prototype status:</strong> new text submissions, job
              status and findings use the backend. Existing sample records,
              brand-library entries, approvals and analytics are illustrative.
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

            <p className="text-sm leading-6 text-slate-500">
              {pageInfo[activeView]}
            </p>

            {activeView === "Overview" && (
              <section className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    {
                      label: "Submissions in this session",
                      value: liveSubmissions.length,
                      note: "Created through the API",
                      icon: "▤",
                      tone: "bg-violet-50 text-violet-700",
                    },
                    {
                      label: "Jobs in progress",
                      value: processingCount,
                      note: "Queued or processing",
                      icon: "◷",
                      tone: "bg-sky-50 text-sky-700",
                    },
                    {
                      label: "Persisted findings",
                      value: liveFindingCount,
                      note: "Loaded from the API",
                      icon: "!",
                      tone: "bg-amber-50 text-amber-700",
                    },
                    {
                      label: "Awaiting human review",
                      value: liveSubmissions.filter(
                        (item) => item.status === "In review",
                      ).length,
                      note: "Not automatically approved",
                      icon: "✓",
                      tone: "bg-emerald-50 text-emerald-700",
                    },
                  ].map((card) => (
                    <article
                      key={card.label}
                      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
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

                      <p className="mt-2 text-xs text-slate-500">
                        {card.note}
                      </p>
                    </article>
                  ))}
                </div>

                <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                  <div className="p-5">
                    <h2 className="font-semibold text-slate-900">
                      Recent live submissions
                    </h2>

                    <p className="mt-1 text-sm text-slate-500">
                      Records created during this browser session.
                    </p>
                  </div>

                  <SubmissionTable
                    rows={liveSubmissions}
                    onSelect={handleOpenSubmission}
                  />
                </section>
              </section>
            )}

            {activeView === "Submissions" && (
              <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
                  <div>
                    <h2 className="font-semibold text-slate-900">
                      Submissions
                    </h2>

                    <p className="mt-1 text-xs text-slate-500">
                      Live submissions and explicitly labelled sample records.
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
                      <option value="Submitted">Submitted</option>
                      <option value="Processing">Processing</option>
                      <option value="In review">In review</option>
                      <option value="Changes requested">
                        Changes requested
                      </option>
                      <option value="Approved">Approved</option>
                      <option value="Failed">Failed</option>
                    </select>
                  </div>
                </div>

                <SubmissionTable
                  rows={filteredSubmissions}
                  onSelect={handleOpenSubmission}
                />
              </section>
            )}

            {activeView === "Review queue" && (
              <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="p-5">
                  <h2 className="font-semibold text-slate-900">
                    Items requiring human attention
                  </h2>

                  <p className="mt-1 text-sm text-slate-500">
                    This list does not perform approval or rejection actions.
                    Authorised review endpoints remain separate work.
                  </p>
                </div>

                <SubmissionTable
                  rows={filteredSubmissions}
                  onSelect={handleOpenSubmission}
                />
              </section>
            )}

            {activeView === "Brand library" && (
              <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {[
                  {
                    title: "Brand voice guidelines",
                    category: "Guidelines",
                    detail:
                      "Approved tone, messaging principles and communication standards.",
                  },
                  {
                    title: "Approved terminology",
                    category: "Terminology",
                    detail:
                      "Preferred terms and language that should be avoided.",
                  },
                  {
                    title: "Verified facts and claims",
                    category: "Facts and claims",
                    detail:
                      "Approved claims and supporting evidence references.",
                  },
                ].map((card) => (
                  <article
                    key={card.title}
                    className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
                  >
                    <p className="text-xs font-medium uppercase tracking-wider text-violet-700">
                      {card.category}
                    </p>

                    <h2 className="mt-2 font-semibold text-slate-900">
                      {card.title}
                    </h2>

                    <p className="mt-2 text-sm leading-6 text-slate-500">
                      {card.detail}
                    </p>

                    <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
                      Reference management not connected yet
                    </p>
                  </article>
                ))}
              </section>
            )}

            {activeView === "Insights" && (
              <section className="grid gap-5 lg:grid-cols-2">
                <article className="rounded-xl border border-slate-200 bg-white p-6">
                  <h2 className="font-semibold text-slate-900">
                    Live analysis summary
                  </h2>

                  <div className="mt-5 space-y-4">
                    {(
                      [
                        ["queued", "Queued"],
                        ["processing", "Processing"],
                        ["completed", "Completed"],
                        ["partial", "Partial"],
                        ["failed", "Failed"],
                      ] as [AnalysisJobStatus, string][]
                    ).map(([jobStatus, label]) => (
                      <div
                        key={jobStatus}
                        className="flex items-center justify-between text-sm"
                      >
                        <span className="text-slate-600">{label}</span>

                        <span className="font-medium text-slate-800">
                          {
                            liveSubmissions.filter(
                              (item) => item.jobStatus === jobStatus,
                            ).length
                          }
                        </span>
                      </div>
                    ))}
                  </div>
                </article>

                <article className="rounded-xl border border-slate-200 bg-white p-6">
                  <h2 className="font-semibold text-slate-900">
                    Analysis limitations
                  </h2>

                  <p className="mt-3 text-sm leading-6 text-slate-600">
                    Deterministic extraction and verification are available for
                    supported structured facts when approved facts are configured.
                    AI-assisted tone and messaging checks depend on optional provider
                    configuration. Unavailable checks are not passing checks.
                  </p>
                </article>
              </section>
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
                    <article className="rounded-xl border border-slate-200 bg-white p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="break-all text-xs text-slate-500">
                            {selectedSubmission.id}
                          </p>

                          <h2 className="mt-1 text-xl font-semibold text-slate-900">
                            {selectedSubmission.title}
                          </h2>

                          <p className="mt-2 text-sm text-slate-500">
                            {selectedSubmission.channel} · {selectedSubmission.owner}
                            {selectedSubmission.versionNumber
                              ? ` · Version ${selectedSubmission.versionNumber}`
                              : ""}
                          </p>
                        </div>

                        <StatusPill status={selectedSubmission.status} />
                      </div>

                      <div className="mt-5 border-t border-slate-100 pt-4">
                        <p className="text-sm font-medium text-slate-700">
                          Findings
                        </p>

                        <p className="mt-1 text-sm text-slate-500">
                          {selectedSubmission.jobId
                            ? `${selectedSubmission.issues} persisted finding(s) loaded`
                            : "This sample record has no connected report."}
                        </p>

                        {selectedSubmission.jobStatus && (
                          <p className="mt-2 text-sm text-slate-600">
                            Analysis status:{" "}
                            <strong>{selectedSubmission.jobStatus}</strong>
                          </p>
                        )}
                      </div>
                    </article>

                    {selectedSubmission.jobStatus === "partial" && (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                        Analysis is partial. Some checks were unavailable.
                        Review the individual findings before making a decision.
                      </div>
                    )}

                    {selectedSubmission.jobId &&
                      (selectedSubmission.jobStatus === "queued" ||
                        selectedSubmission.jobStatus === "processing") && (
                        <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
                          Analysis is running. This report refreshes automatically
                          when the job reaches a terminal state.
                        </div>
                      )}

                    {selectedSubmission.status === "Failed" && (
                      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                        Analysis failed. Check the worker logs and API response.
                      </div>
                    )}

                    {!selectedSubmission.jobId && (
                      <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
                        This is an illustrative sample record. It has no live
                        backend analysis report.
                      </div>
                    )}

                    {selectedSubmission.jobId &&
                      selectedSubmission.findings === undefined &&
                      (selectedSubmission.jobStatus === "completed" ||
                        selectedSubmission.jobStatus === "partial") && (
                        <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
                          Analysis finished. Waiting for the persisted findings
                          endpoint to return the report.
                        </div>
                      )}

                    {selectedSubmission.findings?.length === 0 && (
                      <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
                        Analysis returned no findings for this version.
                      </div>
                    )}

                    {selectedSubmission.findings?.map((finding) => {
                      const affectedText =
                        finding.evidence?.submitted_text ??
                        (finding.location?.kind === "text_range"
                          ? finding.location.matched_text
                          : null);

                      return (
                        <article
                          key={finding.id}
                          className="rounded-xl border border-slate-200 bg-white p-5"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <h3 className="font-semibold capitalize text-slate-900">
                              {finding.category.replaceAll("_", " ")}
                            </h3>

                            <span
                              className={`rounded-full px-3 py-1 text-xs font-medium ${severityColors[finding.severity] ??
                                severityColors.info
                                }`}
                            >
                              {finding.severity} severity
                            </span>
                          </div>

                          <p className="mt-2 text-sm text-slate-500">
                            Result: {finding.result.replaceAll("_", " ")}
                          </p>

                          {affectedText && (
                            <div className="mt-4">
                              <p className="text-sm font-medium text-slate-700">
                                Affected content
                              </p>

                              <p className="mt-1 text-sm text-slate-600">
                                {affectedText}
                              </p>
                            </div>
                          )}

                          <div className="mt-4">
                            <p className="text-sm font-medium text-slate-700">
                              Explanation
                            </p>

                            <p className="mt-1 text-sm leading-6 text-slate-600">
                              {finding.explanation}
                            </p>
                          </div>

                          {(finding.evidence?.approved_reference ||
                            finding.evidence?.source_name) && (
                              <div className="mt-4">
                                <p className="text-sm font-medium text-slate-700">
                                  Reference
                                </p>

                                <p className="mt-1 text-sm text-slate-600">
                                  {finding.evidence.approved_reference ??
                                    finding.evidence.source_name}
                                </p>
                              </div>
                            )}

                          <div className="mt-4 rounded-lg bg-violet-50 p-3">
                            <p className="font-medium text-violet-900">
                              Suggested correction
                            </p>

                            <p className="mt-1 text-sm text-violet-800">
                              {finding.suggested_correction ??
                                "No correction was generated for this finding."}
                            </p>
                          </div>

                          {finding.result === "check_unavailable" && (
                            <p className="mt-3 text-xs text-amber-700">
                              This check could not be completed. Do not treat
                              it as a passing result.
                            </p>
                          )}

                          {finding.requires_human_review && (
                            <p className="mt-3 text-xs text-slate-500">
                              Human review required. AI findings are advisory.
                            </p>
                          )}
                        </article>
                      );
                    })}
                  </>
                ) : (
                  <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
                    No submission selected. Return to submissions and choose an item.
                  </p>
                )}
              </section>
            )}

            <footer className="border-t border-slate-200 pt-4 text-xs leading-5 text-slate-400">
              BrandGuard AI · Prototype · Final approval is not automated.
            </footer>
          </div>
        </section>
      </div>

      {showCreate && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/45 p-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setShowCreate(false);
            }
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
                  Paste your content to submit it for analysis.
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
                  Select the checks relevant to this content. These selections
                  are currently interface-only and are not sent to the analysis API.
                </p>
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
                  required
                  value={draftText}
                  onChange={(event) => setDraftText(event.target.value)}
                  rows={7}
                  placeholder="Paste your marketing copy here..."
                  className="w-full resize-y rounded-lg border border-slate-200 px-3 py-3 text-sm outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />

                <p className="mt-1 text-xs text-slate-500">
                  This prototype currently accepts pasted text; file uploads
                  are not enabled by the backend endpoint.
                </p>
              </div>

              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-900">
                Campaign purpose is retained as a composer selection but is not
                persisted by the current submission API.
              </p>

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