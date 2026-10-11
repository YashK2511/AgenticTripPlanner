'use client'

import { useState } from 'react'

interface ProfileResponse {
  profile: {
    destination: string
    origin: string | null
    start_date: string
    end_date: string
    budget: {
      amount: number
      currency: string
    }
    travelers: Array<{
      id: string
      age_group: string
      gender: string
      accessibility_needs: string[]
    }>
    interests: string[]
    hard_constraints: Record<string, any>
    soft_preferences: Record<string, number>
    missing_fields: string[]
  }
  is_complete: boolean
  clarification_questions: string[]
  request_id: string
}

export default function Home() {
  const [requestText, setRequestText] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ProfileResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!requestText.trim()) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch('http://localhost:8000/api/profile/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_text: requestText }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to extract profile')
      }

      const data: ProfileResponse = await response.json()
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">
          Agentic Trip Planner
        </h1>
        <p className="text-gray-600 mb-8">
          Describe your dream trip in natural language
        </p>

        <form onSubmit={handleSubmit} className="mb-8">
          <textarea
            value={requestText}
            onChange={(e) => setRequestText(e.target.value)}
            placeholder="e.g., I want to plan a family trip to Goa for 4 days starting next month. We are 2 adults and 1 senior who needs wheelchair assistance. Our budget is 1,50,000 INR. We love beaches, seafood, and historic Portuguese churches."
            className="w-full h-32 p-4 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !requestText.trim()}
            className="mt-4 px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Processing...' : 'Plan My Trip'}
          </button>
        </form>

        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 mb-8">
            <strong>Error:</strong> {error}
          </div>
        )}

        {result && (
          <div className="bg-white rounded-lg shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-bold text-gray-900">
                Travel Profile
              </h2>
              <span
                className={`px-3 py-1 rounded-full text-sm font-medium ${
                  result.is_complete
                    ? 'bg-green-100 text-green-800'
                    : 'bg-yellow-100 text-yellow-800'
                }`}
              >
                {result.is_complete ? '✓ Complete' : '⚠ Incomplete'}
              </span>
            </div>

            {!result.is_complete && result.clarification_questions.length > 0 && (
              <div className="mb-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <h3 className="font-semibold text-yellow-900 mb-2">
                  Please clarify:
                </h3>
                <ul className="list-disc list-inside space-y-1 text-yellow-800">
                  {result.clarification_questions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="space-y-4">
              <div>
                <h3 className="font-semibold text-gray-700">Destination</h3>
                <p className="text-gray-900">{result.profile.destination}</p>
              </div>

              {result.profile.origin && (
                <div>
                  <h3 className="font-semibold text-gray-700">From</h3>
                  <p className="text-gray-900">{result.profile.origin}</p>
                </div>
              )}

              <div>
                <h3 className="font-semibold text-gray-700">Dates</h3>
                <p className="text-gray-900">
                  {result.profile.start_date} to {result.profile.end_date}
                </p>
              </div>

              <div>
                <h3 className="font-semibold text-gray-700">Budget</h3>
                <p className="text-gray-900">
                  {result.profile.budget.currency} {result.profile.budget.amount.toLocaleString()}
                </p>
              </div>

              <div>
                <h3 className="font-semibold text-gray-700">Travelers</h3>
                <div className="space-y-2">
                  {result.profile.travelers.map((t) => (
                    <div key={t.id} className="flex items-center gap-2 text-gray-900">
                      <span className="capitalize">{t.age_group}</span>
                      <span>•</span>
                      <span className="capitalize">{t.gender}</span>
                      {t.accessibility_needs.length > 0 && (
                        <>
                          <span>•</span>
                          <span className="text-sm text-gray-600">
                            {t.accessibility_needs.join(', ')}
                          </span>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {result.profile.interests.length > 0 && (
                <div>
                  <h3 className="font-semibold text-gray-700">Interests</h3>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {result.profile.interests.map((interest, i) => (
                      <span
                        key={i}
                        className="px-3 py-1 bg-indigo-100 text-indigo-800 rounded-full text-sm"
                      >
                        {interest}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {Object.keys(result.profile.hard_constraints).length > 0 && (
                <div>
                  <h3 className="font-semibold text-gray-700">Must-Have Constraints</h3>
                  <ul className="list-disc list-inside text-gray-900">
                    {Object.entries(result.profile.hard_constraints).map(([k, v]) => (
                      <li key={k}>
                        {k.replace(/_/g, ' ')}: {String(v)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="mt-4 pt-4 border-t border-gray-200 text-xs text-gray-500">
              Request ID: {result.request_id}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
