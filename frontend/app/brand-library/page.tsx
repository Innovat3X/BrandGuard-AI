"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  approveBrandFact,
  createBrandFact,
  createBrandFactVersion,
  listBrandFacts,
  updateBrandFact,
  type BrandFact,
  type BrandFactDraftInput,
  type BrandFactVersionInput,
  type FactKey,
  type FactKind,
} from "@/services/brand-facts.service";
import {
  approveBrandRule,
  createBrandRule,
  createBrandRuleVersion,
  listBrandRules,
  updateBrandRule,
  type BrandRule,
  type BrandRuleCategory,
  type BrandRuleDraftInput,
  type BrandRuleSeverity,
  type BrandRuleVersionInput,
} from "@/services/brand-rules.service";

type Tab = "facts" | "rules";
type FactEditorMode = "create" | "update" | "version";
type RuleEditorMode = "create" | "update" | "version";

type FactEditor = {
  mode: FactEditorMode;
  factId?: string;
  label: string;
  factText: string;
  sourceUrl: string;
  factKey: FactKey | "";
  value: string;
  unit: string;
};

type RuleEditor = {
  mode: RuleEditorMode;
  ruleId?: string;
  title: string;
  category: BrandRuleCategory;
  description: string;
  ruleText: string;
  severity: BrandRuleSeverity;
};

const FACT_SPECS: Record<FactKey, { label: string; kind: FactKind; units: string[] }> = {
  product_price: { label: "Product price", kind: "currency", units: ["INR", "USD", "EUR", "GBP"] },
  discount_percentage: { label: "Discount percentage", kind: "percentage", units: ["%"] },
  warranty_duration: { label: "Warranty duration", kind: "duration", units: ["year", "years", "month", "months"] },
  battery_life_duration: { label: "Battery life", kind: "duration", units: ["hour", "hours", "day", "days"] },
  product_weight: { label: "Product weight", kind: "quantity", units: ["mg", "g", "kg", "lb"] },
  product_capacity: { label: "Product capacity", kind: "quantity", units: ["ml", "l"] },
};

const inputClass = "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100";
const primaryButton = "rounded-lg bg-violet-700 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-800 disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButton = "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

function latestFactVersion(fact: BrandFact) {
  return fact.versions.reduce((latest, version) =>
    !latest || version.version_number > latest.version_number ? version : latest,
    undefined as BrandFact["versions"][number] | undefined,
  );
}

function latestRuleVersion(rule: BrandRule) {
  return rule.versions.reduce((latest, version) =>
    !latest || version.version_number > latest.version_number ? version : latest,
    undefined as BrandRule["versions"][number] | undefined,
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles = status === "approved"
    ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
    : status === "draft"
      ? "bg-amber-50 text-amber-800 ring-amber-200"
      : "bg-slate-100 text-slate-600 ring-slate-200";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold capitalize ring-1 ring-inset ${styles}`}>{status}</span>;
}

export default function BrandLibraryPage() {
  const [tab, setTab] = useState<Tab>("facts");
  const [facts, setFacts] = useState<BrandFact[]>([]);
  const [rules, setRules] = useState<BrandRule[]>([]);
  const [factsLoading, setFactsLoading] = useState(true);
  const [rulesLoading, setRulesLoading] = useState(true);
  const [factsError, setFactsError] = useState("");
  const [rulesError, setRulesError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [factEditor, setFactEditor] = useState<FactEditor | null>(null);
  const [ruleEditor, setRuleEditor] = useState<RuleEditor | null>(null);

  const loadFacts = useCallback(async () => {
    setFactsLoading(true);
    setFactsError("");
    try {
      setFacts(await listBrandFacts());
    } catch (error) {
      setFactsError(errorMessage(error));
    } finally {
      setFactsLoading(false);
    }
  }, []);

  const loadRules = useCallback(async () => {
    setRulesLoading(true);
    setRulesError("");
    try {
      setRules(await listBrandRules());
    } catch (error) {
      setRulesError(errorMessage(error));
    } finally {
      setRulesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFacts();
    void loadRules();
  }, [loadFacts, loadRules]);

  function startFactCreate() {
    setActionError("");
    setFactEditor({ mode: "create", label: "", factText: "", sourceUrl: "", factKey: "", value: "", unit: "" });
  }

  function startFactEdit(fact: BrandFact) {
    const version = latestFactVersion(fact);
    if (!version || version.status !== "draft") return;
    setActionError("");
    setFactEditor({
      mode: "update",
      factId: fact.id,
      label: fact.label,
      factText: version.fact_text,
      sourceUrl: version.source_url ?? "",
      factKey: version.fact_key ?? "",
      value: version.structured_value?.value ?? "",
      unit: version.structured_value?.unit ?? "",
    });
  }

  function startFactVersion(fact: BrandFact) {
    const version = latestFactVersion(fact);
    setActionError("");
    setFactEditor({
      mode: "version",
      factId: fact.id,
      label: fact.label,
      factText: "",
      sourceUrl: version?.source_url ?? "",
      factKey: version?.fact_key ?? "",
      value: version?.structured_value?.value ?? "",
      unit: version?.structured_value?.unit ?? "",
    });
  }

  async function submitFact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!factEditor) return;
    setSaving(true);
    setActionError("");
    setNotice("");
    try {
      const spec = factEditor.factKey ? FACT_SPECS[factEditor.factKey] : undefined;
      if (spec && (!factEditor.value.trim() || !spec.units.includes(factEditor.unit))) {
        throw new Error("Enter a numeric structured value and choose a valid unit for this fact type.");
      }
      const common = {
        fact_text: factEditor.factText.trim(),
        source_url: factEditor.sourceUrl.trim() || null,
        ...(spec && factEditor.factKey ? {
          fact_key: factEditor.factKey,
          structured_value: { kind: spec.kind, value: factEditor.value.trim(), unit: factEditor.unit },
        } : {}),
      };

      if (factEditor.mode === "create") {
        const input: BrandFactDraftInput = { ...common, label: factEditor.label.trim() };
        await createBrandFact(input);
        setNotice("Draft fact created.");
      } else if (factEditor.factId && factEditor.mode === "update") {
        const input: BrandFactDraftInput = { ...common, label: factEditor.label.trim() };
        await updateBrandFact(factEditor.factId, input);
        setNotice("Draft fact updated.");
      } else if (factEditor.factId) {
        const input: BrandFactVersionInput = common;
        await createBrandFactVersion(factEditor.factId, input);
        setNotice("New draft fact version created.");
      }
      setFactEditor(null);
      await loadFacts();
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function approveFact(factId: string) {
    setSaving(true);
    setActionError("");
    setNotice("");
    try {
      await approveBrandFact(factId);
      setNotice("Fact version approved.");
      await loadFacts();
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  function startRuleCreate() {
    setActionError("");
    setRuleEditor({ mode: "create", title: "", category: "terminology", description: "", ruleText: "", severity: "medium" });
  }

  function startRuleEdit(rule: BrandRule) {
    const version = latestRuleVersion(rule);
    if (!version || version.status !== "draft") return;
    setActionError("");
    setRuleEditor({ mode: "update", ruleId: rule.id, title: rule.title, category: version.category, description: version.description ?? "", ruleText: version.rule_text, severity: version.severity });
  }

  function startRuleVersion(rule: BrandRule) {
    const version = latestRuleVersion(rule);
    setActionError("");
    setRuleEditor({ mode: "version", ruleId: rule.id, title: rule.title, category: version?.category ?? "terminology", description: version?.description ?? "", ruleText: "", severity: version?.severity ?? "medium" });
  }

  async function submitRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ruleEditor) return;
    setSaving(true);
    setActionError("");
    setNotice("");
    try {
      const common = {
        category: ruleEditor.category,
        description: ruleEditor.description.trim() || null,
        rule_text: ruleEditor.ruleText.trim(),
        severity: ruleEditor.severity,
      };
      if (ruleEditor.mode === "create") {
        const input: BrandRuleDraftInput = { ...common, title: ruleEditor.title.trim() };
        await createBrandRule(input);
        setNotice("Draft brand rule created.");
      } else if (ruleEditor.ruleId && ruleEditor.mode === "update") {
        const input: BrandRuleDraftInput = { ...common, title: ruleEditor.title.trim() };
        await updateBrandRule(ruleEditor.ruleId, input);
        setNotice("Draft brand rule updated.");
      } else if (ruleEditor.ruleId) {
        const input: BrandRuleVersionInput = common;
        await createBrandRuleVersion(ruleEditor.ruleId, input);
        setNotice("New draft rule version created.");
      }
      setRuleEditor(null);
      await loadRules();
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function approveRule(ruleId: string) {
    setSaving(true);
    setActionError("");
    setNotice("");
    try {
      await approveBrandRule(ruleId);
      setNotice("Brand rule version approved.");
      await loadRules();
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  const unitOptions = factEditor?.factKey ? FACT_SPECS[factEditor.factKey].units : [];

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link href="/" className="text-sm font-medium text-violet-700 hover:text-violet-900">← Back to dashboard</Link>
            <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-violet-700">BrandGuard AI</p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight">Brand Library</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">Manage organisation-approved facts and brand rules. Every edit is saved as a draft version until an authorised reviewer approves it.</p>
          </div>
          <Link href="/submit-document" className={secondaryButton}>Submit a document</Link>
        </header>

        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
          Access is enforced by the API: administrators and creators can create or edit drafts; administrators and reviewers can approve. If your role is not permitted, the server will reject the action.
        </div>
        {notice && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
        {actionError && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{actionError}</p>}

        <div className="flex gap-2 border-b border-slate-200">
          <button type="button" onClick={() => { setTab("facts"); setActionError(""); }} className={`border-b-2 px-4 py-3 text-sm font-semibold ${tab === "facts" ? "border-violet-700 text-violet-800" : "border-transparent text-slate-500 hover:text-slate-800"}`}>Approved facts &amp; versions</button>
          <button type="button" onClick={() => { setTab("rules"); setActionError(""); }} className={`border-b-2 px-4 py-3 text-sm font-semibold ${tab === "rules" ? "border-violet-700 text-violet-800" : "border-transparent text-slate-500 hover:text-slate-800"}`}>Brand rules</button>
        </div>

        {tab === "facts" && (
          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><h2 className="text-xl font-semibold">Brand facts</h2><p className="text-sm text-slate-500">Product facts and their complete version history.</p></div>
              <div className="flex gap-2"><button type="button" className={secondaryButton} onClick={() => void loadFacts()} disabled={factsLoading}>Refresh</button><button type="button" className={primaryButton} onClick={startFactCreate}>Create fact</button></div>
            </div>
            {factEditor && (
              <form onSubmit={submitFact} className="space-y-4 rounded-xl border border-violet-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between gap-3"><h3 className="font-semibold">{factEditor.mode === "create" ? "Create draft fact" : factEditor.mode === "update" ? "Edit latest draft fact" : "Create new fact version"}</h3><button type="button" className="text-sm text-slate-500 hover:text-slate-800" onClick={() => setFactEditor(null)}>Cancel</button></div>
                {factEditor.mode !== "version" && <label className="block text-sm font-medium">Fact label<input required maxLength={255} className={inputClass} value={factEditor.label} onChange={(event) => setFactEditor({ ...factEditor, label: event.target.value })} /></label>}
                <label className="block text-sm font-medium">Approved fact text<textarea required rows={3} className={inputClass} value={factEditor.factText} onChange={(event) => setFactEditor({ ...factEditor, factText: event.target.value })} placeholder="Example: The product includes a two-year warranty." /></label>
                <label className="block text-sm font-medium">Source URL (optional)<input type="url" className={inputClass} value={factEditor.sourceUrl} onChange={(event) => setFactEditor({ ...factEditor, sourceUrl: event.target.value })} placeholder="https://example.com/product-specification" /></label>
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="block text-sm font-medium sm:col-span-1">Structured fact type (optional)<select className={inputClass} value={factEditor.factKey} onChange={(event) => { const key = event.target.value as FactKey | ""; setFactEditor({ ...factEditor, factKey: key, unit: key ? FACT_SPECS[key].units[0] : "" }); }}><option value="">Not a structured numeric fact</option>{Object.entries(FACT_SPECS).map(([key, spec]) => <option key={key} value={key}>{spec.label}</option>)}</select></label>
                  {factEditor.factKey && <><label className="block text-sm font-medium">Numeric value<input required inputMode="decimal" pattern="[0-9]+(\.[0-9]+)?" className={inputClass} value={factEditor.value} onChange={(event) => setFactEditor({ ...factEditor, value: event.target.value })} placeholder="e.g. 2" /></label><label className="block text-sm font-medium">Unit<select className={inputClass} value={factEditor.unit} onChange={(event) => setFactEditor({ ...factEditor, unit: event.target.value })}>{unitOptions.map((unit) => <option key={unit} value={unit}>{unit}</option>)}</select></label></>}
                </div>
                <p className="text-xs text-slate-500">Structured values are optional, but the fact key and value must be supplied together using a supported type and unit.</p>
                <div className="flex justify-end"><button className={primaryButton} disabled={saving}>{saving ? "Saving…" : "Save draft"}</button></div>
              </form>
            )}
            {factsError && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">Could not load brand facts: {factsError}<button type="button" className="ml-2 underline" onClick={() => void loadFacts()}>Retry</button></div>}
            {factsLoading ? <p className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">Loading facts…</p> : !factsError && facts.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">No brand facts found for this organisation. Create the first fact to get started.</p> : (
              <div className="grid gap-4 md:grid-cols-2">
                {facts.map((fact) => {
                  const latest = latestFactVersion(fact);
                  return <article key={fact.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold">{fact.label}</h3><p className="mt-1 break-all text-xs text-slate-400">{fact.id}</p></div>{latest ? <StatusBadge status={latest.status} /> : <StatusBadge status="archived" />}</div>
                    {latest && <><p className="mt-3 text-sm leading-6 text-slate-700">{latest.fact_text}</p>{latest.structured_value && <p className="mt-2 text-sm font-semibold text-violet-800">Structured value: {latest.structured_value.value} {latest.structured_value.unit} <span className="font-normal text-slate-500">({latest.fact_key?.replaceAll("_", " ")})</span></p>}{latest.source_url && <a href={latest.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block break-all text-xs text-violet-700 underline">View source</a>}<p className="mt-2 text-xs text-slate-500">Latest version: {latest.version_number} · Created {new Date(latest.created_at).toLocaleDateString()}</p></>}
                    <div className="mt-4 flex flex-wrap gap-2">{latest?.status === "draft" && <><button type="button" className={secondaryButton} onClick={() => startFactEdit(fact)}>Edit draft</button><button type="button" className={primaryButton} disabled={saving} onClick={() => void approveFact(fact.id)}>Approve latest draft</button></>}{latest && latest.status !== "draft" && <button type="button" className={secondaryButton} onClick={() => startFactVersion(fact)}>New version</button>}</div>
                    <details className="mt-4 border-t border-slate-100 pt-3"><summary className="cursor-pointer text-sm font-medium text-slate-700">Version history ({fact.versions.length})</summary><ol className="mt-3 space-y-3">{fact.versions.slice().sort((a, b) => a.version_number - b.version_number).map((version) => <li key={version.id} className="border-l-2 border-slate-200 pl-3"><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">Version {version.version_number}</span><StatusBadge status={version.status} /></div><p className="mt-1 text-sm text-slate-600">{version.fact_text}</p>{version.approved_at && <p className="mt-1 text-xs text-slate-400">Approved {new Date(version.approved_at).toLocaleString()}</p>}</li>)}</ol></details>
                  </article>;
                })}
              </div>
            )}
          </section>
        )}

        {tab === "rules" && (
          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">Brand rules</h2><p className="text-sm text-slate-500">Manage tone, terminology and messaging guidance with approval and version history.</p></div><div className="flex gap-2"><button type="button" className={secondaryButton} onClick={() => void loadRules()} disabled={rulesLoading}>Refresh</button><button type="button" className={primaryButton} onClick={startRuleCreate}>Create rule</button></div></div>
            {ruleEditor && (
              <form onSubmit={submitRule} className="space-y-4 rounded-xl border border-violet-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between gap-3"><h3 className="font-semibold">{ruleEditor.mode === "create" ? "Create draft rule" : ruleEditor.mode === "update" ? "Edit latest draft rule" : "Create new rule version"}</h3><button type="button" className="text-sm text-slate-500 hover:text-slate-800" onClick={() => setRuleEditor(null)}>Cancel</button></div>
                {ruleEditor.mode !== "version" && <label className="block text-sm font-medium">Rule title<input required maxLength={255} className={inputClass} value={ruleEditor.title} onChange={(event) => setRuleEditor({ ...ruleEditor, title: event.target.value })} /></label>}
                <div className="grid gap-3 sm:grid-cols-2"><label className="block text-sm font-medium">Category<select className={inputClass} value={ruleEditor.category} onChange={(event) => setRuleEditor({ ...ruleEditor, category: event.target.value as BrandRuleCategory })}><option value="tone">Tone</option><option value="terminology">Terminology</option><option value="messaging">Messaging</option><option value="other">Other</option></select></label><label className="block text-sm font-medium">Severity<select className={inputClass} value={ruleEditor.severity} onChange={(event) => setRuleEditor({ ...ruleEditor, severity: event.target.value as BrandRuleSeverity })}><option value="info">Info</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label></div>
                <label className="block text-sm font-medium">Description (optional)<input maxLength={2000} className={inputClass} value={ruleEditor.description} onChange={(event) => setRuleEditor({ ...ruleEditor, description: event.target.value })} /></label>
                <label className="block text-sm font-medium">Rule text<textarea required maxLength={10000} rows={4} className={inputClass} value={ruleEditor.ruleText} onChange={(event) => setRuleEditor({ ...ruleEditor, ruleText: event.target.value })} placeholder="Describe the required brand behaviour or terminology guidance." /></label>
                <div className="flex justify-end"><button className={primaryButton} disabled={saving}>{saving ? "Saving…" : "Save draft"}</button></div>
              </form>
            )}
            {rulesError && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">Could not load brand rules: {rulesError}<button type="button" className="ml-2 underline" onClick={() => void loadRules()}>Retry</button></div>}
            {rulesLoading ? <p className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">Loading rules…</p> : !rulesError && rules.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">No brand rules found for this organisation. Create the first rule to get started.</p> : (
              <div className="grid gap-4 md:grid-cols-2">{rules.map((rule) => {
                const latest = latestRuleVersion(rule);
                return <article key={rule.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold">{rule.title}</h3><p className="mt-1 text-xs text-slate-400">{rule.id}</p></div>{latest ? <StatusBadge status={latest.status} /> : <StatusBadge status="archived" />}</div>
                  {latest && <><div className="mt-3 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-slate-100 px-2 py-1 capitalize">{latest.category}</span><span className="rounded-full bg-slate-100 px-2 py-1 capitalize">{latest.severity} severity</span><span className="rounded-full bg-slate-100 px-2 py-1">Version {latest.version_number}</span></div>{latest.description && <p className="mt-3 text-sm text-slate-500">{latest.description}</p>}<p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{latest.rule_text}</p></>}
                  <div className="mt-4 flex flex-wrap gap-2">{latest?.status === "draft" && <><button type="button" className={secondaryButton} onClick={() => startRuleEdit(rule)}>Edit draft</button><button type="button" className={primaryButton} disabled={saving} onClick={() => void approveRule(rule.id)}>Approve latest draft</button></>}{latest && latest.status !== "draft" && <button type="button" className={secondaryButton} onClick={() => startRuleVersion(rule)}>New version</button>}</div>
                  <details className="mt-4 border-t border-slate-100 pt-3"><summary className="cursor-pointer text-sm font-medium text-slate-700">Version history ({rule.versions.length})</summary><ol className="mt-3 space-y-3">{rule.versions.slice().sort((a, b) => a.version_number - b.version_number).map((version) => <li key={version.id} className="border-l-2 border-slate-200 pl-3"><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">Version {version.version_number}</span><StatusBadge status={version.status} /></div><p className="mt-1 text-sm text-slate-600">{version.rule_text}</p>{version.approved_at && <p className="mt-1 text-xs text-slate-400">Approved {new Date(version.approved_at).toLocaleString()}</p>}</li>)}</ol></details>
                </article>;
              })}</div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
