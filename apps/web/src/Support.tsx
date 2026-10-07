import React from 'react';

export default function Support() {
  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 py-16 px-6 sm:px-12">
      <div className="max-w-3xl mx-auto space-y-12">
        
        {/* Header */}
        <div className="text-center space-y-4">
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500">
            PromptEngine Support
          </h1>
          <p className="text-lg text-slate-400">
            We are here to help you optimize your AI workflows.
          </p>
        </div>

        {/* Contact Section */}
        <section className="bg-slate-800/50 p-8 rounded-2xl border border-slate-700 shadow-xl">
          <h2 className="text-2xl font-semibold mb-4 text-white">Get in Touch</h2>
          <p className="text-slate-300 mb-6">
            Experiencing a bug, have a billing question, or want to request a feature? Reach out to our engineering team directly.
          </p>
          <div className="flex items-center space-x-3">
            <svg className="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <a href="mailto:support@promptlogic.io" className="text-lg font-medium text-blue-400 hover:text-blue-300 transition-colors">
              support@promptlogic.io
            </a>
            <br> </br>
            <a href="mailto:business@telitesystems.com" className="text-lg font-medium text-blue-400 hover:text-blue-300 transition-colors">
              business@telitesystems.com
            </a>
          </div>
          <p className="text-sm text-slate-500 mt-4">Average response time: 24-48 hours during business days.</p>
        </section>

        {/* FAQ Section */}
        <section className="space-y-6">
          <h2 className="text-2xl font-semibold text-white">Frequently Asked Questions</h2>
          
          <div className="grid gap-4">
            <div className="bg-slate-800/30 p-6 rounded-xl border border-slate-700/50">
              <h3 className="font-semibold text-lg text-blue-300">How do I connect the Chrome Extension?</h3>
              <p className="text-slate-400 mt-2">
                After installing the extension from the Web Store, click the PromptEngine icon in your browser toolbar. Log in using your PromptLogic account credentials to securely sync your workspaces and preset library.
              </p>
            </div>

            <div className="bg-slate-800/30 p-6 rounded-xl border border-slate-700/50">
              <h3 className="font-semibold text-lg text-blue-300">Where is my prompt history saved?</h3>
              <p className="text-slate-400 mt-2">
                All generated prompts and refinements are securely logged to your account's cloud database. You can view, search, and export your historical dataset directly from the Web Dashboard.
              </p>
            </div>

            <div className="bg-slate-800/30 p-6 rounded-xl border border-slate-700/50">
              <h3 className="font-semibold text-lg text-blue-300">How do team workspaces function?</h3>
              <p className="text-slate-400 mt-2">
                Workspaces allow you to share prompt templates across your organization. Only users with Admin or Owner roles can modify shared presets, ensuring your company's core prompts remain standardized.
              </p>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
