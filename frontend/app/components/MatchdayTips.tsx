"use client";

import { useState } from "react";
import axios from "axios";

type Tip = {
  tip_id: number;
  venue_id: number;
  tip: string;
  helpful_votes: number;
  report_count: number;
  status: string;
  created_at: string;
};

type Props = {
  tips?: Tip[];
};

export default function MatchdayTips({ tips = [] }: Props) {
  const [tipList, setTipList] = useState<Tip[]>(tips);
  const [showForm, setShowForm] = useState(false);
  const [newTip, setNewTip] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const markHelpful = async (tipId: number) => {
    try {
      const response = await axios.post(
        `http://localhost:8000/tips/${tipId}/helpful`
      );

      setTipList((currentTips) =>
        currentTips.map((tip) =>
          tip.tip_id === tipId ? response.data : tip
        )
      );
    } catch (error) {
      console.error("Could not mark tip as helpful:", error);
    }
  };

  const reportTip = async (tipId: number) => {
    try {
      const response = await axios.post(
        `http://localhost:8000/tips/${tipId}/report`
      );

      setTipList((currentTips) =>
        currentTips.map((tip) =>
          tip.tip_id === tipId
            ? {
                ...tip,
                report_count: response.data.report_count,
                status: response.data.status,
              }
            : tip
        )
      );
    } catch (error) {
      console.error("Could not report tip:", error);
    }
  };

  const submitTip = async () => {
    const trimmedTip = newTip.trim();

    if (!trimmedTip) {
      setError("Please enter a tip before submitting.");
      return;
    }

    setSubmitting(true);
    setError("");

    try {
      const response = await axios.post(
        "http://localhost:8000/tips",
        {
          venue_id: Number(window.location.pathname.split("/").pop()),
          tip: trimmedTip,
        }
      );

      setTipList((currentTips) => [
        response.data,
        ...currentTips,
      ]);

      setNewTip("");
      setShowForm(false);
    } catch (error) {
      console.error("Could not create tip:", error);
      setError("Could not submit your tip. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        border: "1px solid #ddd",
        borderRadius: "12px",
        padding: "20px",
        marginBottom: "24px",
      }}
    >
      <h2>💡 Matchday Tips</h2>

      <button
        onClick={() => {
          setShowForm(!showForm);
          setError("");
        }}
        style={{
          marginTop: "12px",
          marginBottom: "16px",
          padding: "10px 18px",
          cursor: "pointer",
        }}
      >
        {showForm ? "Cancel" : "Add a tip"}
      </button>

      {showForm && (
        <div
          style={{
            marginBottom: "20px",
            padding: "16px",
            background: "#f8f8f8",
            borderRadius: "8px",
          }}
        >
          <textarea
            value={newTip}
            onChange={(event) => setNewTip(event.target.value)}
            placeholder="Share useful advice for other away fans..."
            rows={4}
            style={{
              width: "100%",
              padding: "10px",
              boxSizing: "border-box",
              resize: "vertical",
            }}
          />

          {error && (
            <p style={{ color: "red" }}>
              {error}
            </p>
          )}

          <button
            onClick={submitTip}
            disabled={submitting}
            style={{
              marginTop: "10px",
              padding: "10px 18px",
              cursor: submitting ? "default" : "pointer",
            }}
          >
            {submitting ? "Submitting..." : "Submit tip"}
          </button>
        </div>
      )}

      {tipList.length === 0 ? (
        <p>No tips yet. Be the first to add one.</p>
      ) : (
        <div>
          {tipList.map((tip) => (
            <div
              key={tip.tip_id}
              style={{
                borderTop: "1px solid #eee",
                padding: "16px 0",
              }}
            >
              <p>{tip.tip}</p>

              <div
                style={{
                  display: "flex",
                  gap: "12px",
                  alignItems: "center",
                }}
              >
                <button
                  onClick={() => markHelpful(tip.tip_id)}
                  style={{
                    padding: "6px 10px",
                    cursor: "pointer",
                  }}
                >
                  👍 Helpful ({tip.helpful_votes})
                </button>

                <button
                  onClick={() => reportTip(tip.tip_id)}
                  style={{
                    padding: "6px 10px",
                    cursor: "pointer",
                  }}
                >
                  🚩 Report
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}