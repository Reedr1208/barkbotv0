import React, { useState } from "react";
import { Heart, Info, Settings2, Shuffle, Send, ExternalLink, Sparkles, ShieldCheck, PawPrint, MessageCircle } from "lucide-react";
import { motion } from "framer-motion";

const traits = ["Loyal sidekick", "Older dog-savvy kids", "Boundary aware", "Likes to stay close"];
const quickPrompts = [
  "What home fits Jaxon best?",
  "Is Jaxon good with kids?",
  "What should I know before meeting him?",
];

export default function ChattyhoundRedesignMockup() {
  const [activeTab, setActiveTab] = useState("about");

  return (
    <div className="min-h-screen bg-slate-950 text-white flex justify-center px-4 py-6">
      <div className="w-full max-w-[430px] rounded-[2rem] overflow-hidden bg-slate-900 shadow-2xl ring-1 ring-white/10">
        <header className="sticky top-0 z-20 bg-slate-950/85 backdrop-blur border-b border-white/10 px-5 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400 font-bold">Chattyhound</p>
              <h1 className="text-xl font-black leading-tight">Find your match</h1>
            </div>
            <button className="rounded-full bg-indigo-500 hover:bg-indigo-400 px-4 py-2 text-sm font-extrabold shadow-lg shadow-indigo-500/25 flex items-center gap-2">
              <Shuffle size={16} /> Shuffle
            </button>
          </div>
        </header>

        <main className="pb-28">
          <section className="relative">
            <img
              src="https://images.unsplash.com/photo-1593134257782-e89567b7718a?q=80&w=1200&auto=format&fit=crop"
              alt="Small white and tan rescue dog"
              className="h-72 w-full object-cover object-center"
            />
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-900 via-slate-900/70 to-transparent p-5 pt-24">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <div className="mb-2 inline-flex items-center gap-1 rounded-full bg-emerald-400/15 px-3 py-1 text-sm font-black text-emerald-300 ring-1 ring-emerald-300/20">
                    <Sparkles size={14} /> Strong match
                  </div>
                  <h2 className="text-5xl font-black tracking-tight">Jaxon</h2>
                  <p className="text-slate-300 font-bold">A803019 • PACC</p>
                </div>
                <button className="rounded-full bg-white text-slate-950 p-4 shadow-xl" aria-label="Save Jaxon">
                  <Heart size={22} />
                </button>
              </div>
            </div>
          </section>

          <section className="px-5 py-5 space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <Stat label="Sex" value="Male" sub="Unaltered" />
              <Stat label="Age" value="~6 yrs" sub="Adult" warning />
              <Stat label="Weight" value="23 lb" sub="Small" />
            </div>

            <div className="rounded-3xl bg-slate-800/80 p-4 ring-1 ring-white/10">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl bg-emerald-400/15 p-2 text-emerald-300">
                  <ShieldCheck size={22} />
                </div>
                <div className="min-w-0">
                  <h3 className="font-black text-lg">Why Jaxon may fit you</h3>
                  <p className="mt-1 text-slate-300 leading-relaxed">
                    Jaxon sounds like a loyal, sidekick-style companion who wants to stay close and do best with people who respect his boundaries.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {traits.map((trait) => (
                  <span key={trait} className="rounded-full bg-slate-900/70 px-3 py-2 text-sm font-bold text-slate-200 ring-1 ring-white/10">
                    {trait}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <button className="rounded-2xl bg-slate-800 p-4 text-left ring-1 ring-white/10 hover:bg-slate-700">
                <PawPrint className="mb-3 text-indigo-300" />
                <p className="font-black">View profile</p>
                <p className="text-sm text-slate-400">Official shelter page</p>
              </button>
              <button className="rounded-2xl bg-indigo-500 p-4 text-left shadow-lg shadow-indigo-500/25 hover:bg-indigo-400">
                <MessageCircle className="mb-3" />
                <p className="font-black">Ask Jaxon</p>
                <p className="text-sm text-indigo-100">Start with prompts</p>
              </button>
            </div>
          </section>

          <section className="border-t border-white/10 px-5 py-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-2xl font-black">Chat with Jaxon</h3>
              <div className="flex gap-2 rounded-full bg-slate-800 p-1 ring-1 ring-white/10">
                <Tab active={activeTab === "about"} onClick={() => setActiveTab("about")} icon={<Info size={16} />} label="About" />
                <Tab active={activeTab === "prefs"} onClick={() => setActiveTab("prefs")} icon={<Settings2 size={16} />} label="Fit" />
              </div>
            </div>

            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-[1.75rem] bg-slate-800 p-4 ring-1 ring-white/10"
            >
              <div className="flex gap-3">
                <div className="h-10 w-10 shrink-0 rounded-full bg-gradient-to-br from-indigo-400 to-emerald-300 flex items-center justify-center text-slate-950 font-black">
                  J
                </div>
                <div className="rounded-3xl rounded-tl-md bg-slate-700 px-4 py-3 text-slate-50 leading-relaxed">
                  Hi, I’m Jaxon. I can help you understand my ideal home, energy level, boundaries, and what to ask the shelter before meeting me.
                </div>
              </div>
              <div className="mt-4 space-y-2">
                {quickPrompts.map((prompt) => (
                  <button key={prompt} className="w-full rounded-2xl bg-slate-900/70 px-4 py-3 text-left text-sm font-bold text-slate-200 ring-1 ring-white/10 hover:bg-slate-900">
                    {prompt}
                  </button>
                ))}
              </div>
            </motion.div>
          </section>
        </main>

        <footer className="fixed bottom-4 left-1/2 z-30 w-[calc(100%-2rem)] max-w-[390px] -translate-x-1/2">
          <div className="rounded-full bg-slate-950/95 p-2 shadow-2xl ring-1 ring-white/15 backdrop-blur">
            <div className="flex items-center gap-2">
              <input
                aria-label="Ask Jaxon a question"
                placeholder="Ask about Jaxon…"
                className="min-w-0 flex-1 rounded-full bg-slate-800 px-5 py-4 text-base font-semibold text-white outline-none placeholder:text-slate-500"
              />
              <button className="rounded-full bg-indigo-500 p-4 shadow-lg shadow-indigo-500/25" aria-label="Send message">
                <Send size={20} />
              </button>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}

function Stat({ label, value, sub, warning }) {
  return (
    <div className={`rounded-2xl p-3 ring-1 ${warning ? "bg-amber-400/10 ring-amber-300/30" : "bg-emerald-400/10 ring-emerald-300/20"}`}>
      <p className="text-[11px] uppercase tracking-widest text-slate-400 font-black">{label}</p>
      <p className="mt-1 text-lg font-black leading-tight">{value}</p>
      <p className="text-xs text-slate-400 font-bold">{sub}</p>
    </div>
  );
}

function Tab({ active, onClick, icon, label }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-black transition ${active ? "bg-white text-slate-950" : "text-slate-300 hover:text-white"}`}
    >
      {icon}
      {label}
    </button>
  );
}
