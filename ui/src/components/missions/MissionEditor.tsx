import { useState } from "react";
import Card from "../shared/Card";
import { api } from "../../api/client";
import type { Mission } from "../../api/types";
import { PRIORITIES, type Priority } from "../../lib/verbs";

const SYSTEM_PROMPT_MAX = 8192;

const EXAMPLE_PROMPT =
  "You are an autonomous UAV operating over coastal water. Fly the assigned area and look for any boats or large objects on the water surface. Report a Contact event when you find one with a short description (size, color, heading if visible). Send a Sitrep every 60s with a brief scene description. Respect ROE-default: observe and report only.";

type Props = {
  onCreated: (m: Mission) => void;
};

export default function MissionEditor({ onCreated }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [objectives, setObjectives] = useState("");
  const [targetSpecs, setTargetSpecs] = useState("");
  const [areaGeoJson, setAreaGeoJson] = useState("");
  const [priority, setPriority] = useState<Priority>("ROUTINE");
  const [roeProfile, setRoeProfile] = useState("roe-default");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const promptBytes = new TextEncoder().encode(systemPrompt).length;
  const promptOverflow = promptBytes > SYSTEM_PROMPT_MAX;
  const canSubmit =
    !submitting && name.trim().length > 0 && systemPrompt.trim().length > 0 && !promptOverflow;

  function loadExample() {
    if (!name.trim()) setName("Demo - Boat Watch");
    if (!description.trim()) setDescription("Plain-English boat-spotting mission.");
    if (!systemPrompt.trim()) setSystemPrompt(EXAMPLE_PROMPT);
    if (!targetSpecs.trim()) setTargetSpecs("small boats; large floating objects; persons in the water");
  }

  async function submit() {
    setError(null);
    setSubmitting(true);
    try {
      const m = await api.createMission({
        name: name.trim(),
        description: description.trim() || "none",
        system_prompt: systemPrompt,
        objectives: objectives.trim() || undefined,
        target_specs: targetSpecs.trim() || undefined,
        area_geo_json: areaGeoJson.trim() || undefined,
        priority,
        roe_profile: roeProfile.trim() || "roe-default",
      });
      onCreated(m);
      // Reset form for the next mission.
      setName("");
      setDescription("");
      setSystemPrompt("");
      setObjectives("");
      setTargetSpecs("");
      setAreaGeoJson("");
      setPriority("ROUTINE");
      setRoeProfile("roe-default");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-100">New Mission</h3>
        <button
          type="button"
          onClick={loadExample}
          className="text-[10px] text-blue-400 hover:text-blue-300"
        >
          load example
        </button>
      </div>

      <div>
        <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">Name *</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Harbor Recon"
          className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none"
        />
      </div>

      <div>
        <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">Description</label>
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="One-line summary"
          className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-[10px] text-gray-500 uppercase tracking-wide">System Prompt *</label>
          <span
            className={`text-[10px] font-mono ${
              promptOverflow ? "text-red-400" : promptBytes > SYSTEM_PROMPT_MAX * 0.8 ? "text-amber-400" : "text-gray-500"
            }`}
          >
            {promptBytes} / {SYSTEM_PROMPT_MAX} B
          </span>
        </div>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={8}
          placeholder='e.g. "Fly over water and report any boats."'
          className={`w-full bg-gray-950 border rounded px-2 py-1 text-xs text-gray-100 outline-none font-mono leading-snug ${
            promptOverflow ? "border-red-700 focus:border-red-500" : "border-gray-700 focus:border-blue-600"
          }`}
        />
        <p className="text-[10px] text-gray-500 mt-1">
          Becomes the top of the on-board LLM's system prompt when assigned.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">Priority</label>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
            className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none"
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">ROE Profile</label>
          <input
            type="text"
            value={roeProfile}
            onChange={(e) => setRoeProfile(e.target.value)}
            className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none"
          />
        </div>
      </div>

      <details className="border-t border-gray-800 pt-2">
        <summary className="text-[10px] text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-300">
          Optional structure (objectives / targets / area)
        </summary>
        <div className="space-y-2 mt-2">
          <div>
            <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">Objectives</label>
            <textarea
              value={objectives}
              onChange={(e) => setObjectives(e.target.value)}
              rows={2}
              placeholder="Free text or JSON"
              className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none font-mono leading-snug"
            />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">Target Specs</label>
            <textarea
              value={targetSpecs}
              onChange={(e) => setTargetSpecs(e.target.value)}
              rows={2}
              placeholder='e.g. "small boats; persons in water"'
              className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none font-mono leading-snug"
            />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">Area (GeoJSON)</label>
            <textarea
              value={areaGeoJson}
              onChange={(e) => setAreaGeoJson(e.target.value)}
              rows={3}
              placeholder='{"type":"Polygon","coordinates":[[[lon,lat],...]]}'
              className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none font-mono leading-snug"
            />
          </div>
        </div>
      </details>

      <button
        type="button"
        disabled={!canSubmit}
        onClick={submit}
        className={`w-full text-xs font-medium px-3 py-2 rounded transition-colors ${
          canSubmit
            ? "bg-blue-600 text-white hover:bg-blue-500"
            : "bg-gray-800 text-gray-500 cursor-not-allowed"
        }`}
      >
        {submitting
          ? "Creating…"
          : !name.trim()
            ? "Name required"
            : !systemPrompt.trim()
              ? "System prompt required"
              : promptOverflow
                ? `Prompt too large (${promptBytes} B)`
                : "Create Mission"}
      </button>

      {error && (
        <div className="px-2 py-1.5 rounded bg-red-900/30 border border-red-800/50 text-red-300 text-[11px]">
          {error}
        </div>
      )}
    </Card>
  );
}
