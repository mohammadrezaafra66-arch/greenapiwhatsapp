import React from "react";

// C1.4 — one component crash must not white-screen the whole app.
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    console.error("UI error boundary caught:", error, info);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-10 text-center space-y-4" dir="rtl">
          <p className="text-4xl">😕</p>
          <p className="text-slate-300">مشکلی در نمایش این بخش پیش آمد.</p>
          <p className="text-xs text-slate-500 font-mono break-words max-w-md mx-auto">
            {String(this.state.error?.message || this.state.error)}
          </p>
          <button className="btn-primary" onClick={() => window.location.reload()}>
            تازه‌سازی صفحه
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
