"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import api from "../../lib/api";

type Venue = {
  venue_id: number;
  name: string;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
};

type MyReview = {
  review_id: number;
  venue_id: number;
  venue_name: string;
  venue_city: string | null;

  fixture_id: number | null;
  fixture_date: string | null;

  home_team: string | null;
  away_team: string | null;

  visit_date: string | null;

  recommend: boolean | null;

  overall_score: number | null;
  atmosphere_score: number | null;
  pubs_score: number | null;
  getting_there_score: number | null;
  facilities_score: number | null;

  created_at: string | null;
};

export default function MyStadiumsPage() {
  const searchParams = useSearchParams();

  const reviewVenueId =
  searchParams.get("review");
  
  const [reviews, setReviews] =
    useState<MyReview[]>([]);

  const [query, setQuery] =
    useState("");

  const [venues, setVenues] =
    useState<Venue[]>([]);

  const [selectedVenue, setSelectedVenue] =
    useState<Venue | null>(null);

  const [visitDate, setVisitDate] =
    useState("");

  const [loading, setLoading] =
    useState(true);

  const [searching, setSearching] =
    useState(false);

  const [saving, setSaving] =
    useState(false);

  const [reviewingVenueId, setReviewingVenueId] =
    useState<number | null>(null);

  const [reviewAtmosphere, setReviewAtmosphere] =
    useState<number | null>(null);

  const [reviewPubs, setReviewPubs] =
    useState<number | null>(null);

  const [reviewGettingThere, setReviewGettingThere] =
    useState<number | null>(null);

  const [reviewFacilities, setReviewFacilities] =
    useState<number | null>(null);

  const [reviewRecommend, setReviewRecommend] =
    useState<boolean | null>(null);

  const [reviewSaving, setReviewSaving] =
    useState(false);

  const [error, setError] =
    useState("");

  // ---------------------------------------------------------
  // Load user's stadiums
  // ---------------------------------------------------------

  const loadReviews = () => {
    setLoading(true);

    api
      .get("/session")
      .then(() => {
        return api.get("/my-reviews");
      })
.then((response) => {
  const loadedReviews =
    response.data as MyReview[];

  setReviews(loadedReviews);

  if (reviewVenueId) {
    const venueId = Number(
      reviewVenueId
    );

    const review = loadedReviews.find(
      (item) =>
        Number(item.venue_id) === venueId
    );

    if (review) {
      openReviewForm(review);
    }
  }
})
      .catch((error) => {
        console.error(
          "My stadiums loading error:",
          error
        );

        setError(
          "Unable to load your stadiums."
        );
      })
      .finally(() => {
        setLoading(false);
      });
  };

useEffect(() => {
  loadReviews();
}, [reviewVenueId]);

  // ---------------------------------------------------------
  // Open review form
  // ---------------------------------------------------------

  const openReviewForm = (
    review: MyReview
  ) => {
    setReviewingVenueId(
      review.venue_id
    );

    setReviewAtmosphere(
      review.atmosphere_score
    );

    setReviewPubs(
      review.pubs_score
    );

    setReviewGettingThere(
      review.getting_there_score
    );

    setReviewFacilities(
      review.facilities_score
    );

    setReviewRecommend(
      review.recommend
    );

    setError("");
  };

  // ---------------------------------------------------------
  // Close review form
  // ---------------------------------------------------------

  const closeReviewForm = () => {
    setReviewingVenueId(null);
    setReviewAtmosphere(null);
    setReviewPubs(null);
    setReviewGettingThere(null);
    setReviewFacilities(null);
    setReviewRecommend(null);
  };

  // ---------------------------------------------------------
  // Search venues
  // ---------------------------------------------------------

  const searchVenues = () => {
    const trimmedQuery =
      query.trim();

    if (trimmedQuery.length < 2) {
      setVenues([]);
      return;
    }

    setSearching(true);
    setError("");

    api
      .get("/venues/search", {
        params: {
          q: trimmedQuery,
          limit: 20,
        },
      })
      .then((response) => {
        setVenues(response.data);
      })
      .catch((error) => {
        console.error(
          "Venue search error:",
          error
        );

        setError(
          "Unable to search for stadiums."
        );
      })
      .finally(() => {
        setSearching(false);
      });
  };

  // ---------------------------------------------------------
  // Add stadium
  // ---------------------------------------------------------

  const addStadium = () => {
    if (!selectedVenue) {
      return;
    }

    const alreadyAdded =
      reviews.some(
        (review) =>
          review.venue_id ===
          selectedVenue.venue_id
      );

    if (alreadyAdded) {
      setError(
        "This stadium is already in your stadiums."
      );

      return;
    }

    setSaving(true);
    setError("");

    const addedVenueId =
      selectedVenue.venue_id;

    api
      .post(
        `/venues/${addedVenueId}/away-day-reviews`,
        {
          venue_id:
            addedVenueId,
          visit_date:
            visitDate || null,
        }
      )
      .then(() => {
        // Reload the user's stadiums so the
        // newly-created visit has the full
        // /my-reviews response structure.
        return api.get("/my-reviews");
      })
      .then((response) => {
        const updatedReviews =
          response.data as MyReview[];

        setReviews(updatedReviews);

        // Find the newly-added stadium.
        const newReview =
          updatedReviews.find(
            (review) =>
              review.venue_id ===
              addedVenueId
          );

        // Clear the add-stadium UI.
        setSelectedVenue(null);
        setVisitDate("");
        setQuery("");
        setVenues([]);

        // Immediately open the review form.
        if (newReview) {
          openReviewForm(
            newReview
          );
        }
      })
      .catch((error) => {
        console.error(
          "Add stadium error:",
          error
        );

        if (
          error.response?.status === 409
        ) {
          setError(
            "This stadium is already in your stadiums."
          );
        } else {
          setError(
            "Unable to add this stadium."
          );
        }
      })
      .finally(() => {
        setSaving(false);
      });
  };

  // ---------------------------------------------------------
  // Submit review
  // ---------------------------------------------------------

  const submitReview = () => {
    if (
      reviewingVenueId === null
    ) {
      return;
    }

    setReviewSaving(true);
    setError("");

    api
      .patch(
        `/venues/${reviewingVenueId}/away-day-reviews`,
        {
          recommend:
            reviewRecommend,
          atmosphere_score:
            reviewAtmosphere,
          pubs_score:
            reviewPubs,
          getting_there_score:
            reviewGettingThere,
          facilities_score:
            reviewFacilities,
        }
      )
      .then(() => {
        return api.get("/my-reviews");
      })
      .then((response) => {
        setReviews(response.data);

        closeReviewForm();
      })
      .catch((error) => {
        console.error(
          "Review submission error:",
          error
        );

        setError(
          "Unable to save your review."
        );
      })
      .finally(() => {
        setReviewSaving(false);
      });
  };

  // ---------------------------------------------------------
  // Selected venue duplicate state
  // ---------------------------------------------------------

  const alreadyAdded =
    selectedVenue !== null &&
    reviews.some(
      (review) =>
        review.venue_id ===
        selectedVenue.venue_id
    );

  // ---------------------------------------------------------
  // Calculate live overall score
  // ---------------------------------------------------------

  const completedReviewScores = [
    reviewAtmosphere,
    reviewPubs,
    reviewGettingThere,
    reviewFacilities,
  ].filter(
    (score): score is number =>
      score !== null
  );

  const calculatedOverall =
    completedReviewScores.length > 0
      ? (
          completedReviewScores.reduce(
            (total, score) =>
              total + score,
            0
          ) /
          completedReviewScores.length
        ).toFixed(1)
      : null;

  // ---------------------------------------------------------
  // UI
  // ---------------------------------------------------------


  return (
    <main className="max-w-4xl mx-auto p-6">

      {/* =====================================================
          MY STADIUMS
          ===================================================== */}

      <h1 className="text-3xl font-bold mb-2">
        My Stadiums
      </h1>

      <p className="text-gray-600 mb-8">
        Stadiums you've visited.
      </p>

      {/* Loading */}

      {loading && (
        <p className="text-gray-600 mb-8">
          Loading your stadiums...
        </p>
      )}

      {/* No stadiums */}

      {!loading &&
        reviews.length === 0 && (
          <div className="border rounded-xl p-6 mb-10">
            <p className="text-gray-600">
              No stadiums logged yet.
            </p>
          </div>
        )}

      {/* Stadium list */}

      {!loading &&
        reviews.length > 0 && (
          <div className="space-y-4 mb-12">

            {reviews.map((review) => {

              const hasReview =
                review.recommend !== null ||
                review.overall_score !== null ||
                review.atmosphere_score !== null ||
                review.pubs_score !== null ||
                review.getting_there_score !== null ||
                review.facilities_score !== null;

              const isReviewing =
                reviewingVenueId ===
                review.venue_id;

              return (
                <div
                  key={review.review_id}
                  className="border rounded-xl p-5"
                >

                  {/* Stadium header */}

                  <div className="flex justify-between items-start gap-4">

                    <div>
                      <h2 className="text-xl font-semibold">
                        {review.venue_name}
                      </h2>

                      {review.venue_city && (
                        <p className="text-gray-600">
                          {review.venue_city}
                        </p>
                      )}

                      {review.visit_date && (
                        <p className="text-sm text-gray-500 mt-2">
                          Visited{" "}
                          {new Date(
                            review.visit_date
                          ).toLocaleDateString()}
                        </p>
                      )}
                    </div>

                    <span className="text-sm font-medium">
                      ✓ Visited
                    </span>

                  </div>

                  {/* Review status */}

                  <div className="mt-4">

                    {hasReview ? (
                      <div>

                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-sm font-medium">
                            ✓ Reviewed
                          </span>
                        </div>

{review.overall_score !== null && (
  <p className="text-lg font-semibold">
    🎟️ {Number(review.overall_score).toFixed(1)}
  </p>
)}

                        {review.recommend !== null && (
                          <p className="text-sm text-gray-600">
                            {review.recommend
                              ? "Recommended"
                              : "Not recommended"}
                          </p>
                        )}

                        {!isReviewing && (
                          <button
                            type="button"
                            onClick={() =>
                              openReviewForm(
                                review
                              )
                            }
                            className="border rounded-lg px-4 py-2 mt-3"
                          >
                            Edit Review
                          </button>
                        )}

                      </div>
                    ) : (
                      <div>

                        <p className="text-gray-600 mb-3">
                          Review incomplete.
                        </p>

                        {!isReviewing && (
                          <button
                            type="button"
                            onClick={() =>
                              openReviewForm(
                                review
                              )
                            }
                            className="border rounded-lg px-4 py-2"
                          >
                            Review Stadium
                          </button>
                        )}

                      </div>
                    )}

                  </div>

                  {/* Review form */}

                  {isReviewing && (
                    <div className="mt-6 border-t pt-6">

                      <h3 className="text-lg font-semibold mb-2">
                        How was your away day?
                      </h3>

                      <p className="text-gray-600 mb-6">
                        Rate your experience from
                        1 to 10.
                      </p>

{/* Terrace Rating */}

<div className="mb-6">

  <label className="block font-medium mb-2 text-white">
    Terrace Rating
  </label>

  <div className="text-2xl font-bold text-white">
    {calculatedOverall !== null
      ? `🎟️ ${calculatedOverall}`
      : "🎟️ —"}
  </div>

</div>

      {/* Atmosphere */}

                      <div className="mb-6">

                        <label className="block font-medium mb-2">
                          Atmosphere
                        </label>

                        <div className="flex gap-2 flex-wrap">

                          {[1,2,3,4,5,6,7,8,9,10].map(
                            (score) => (
                              <button
                                key={score}
                                type="button"
                                onClick={() =>
                                  setReviewAtmosphere(
                                    score
                                  )
                                }
                               className={`border rounded-lg px-3 py-2 ${
  reviewAtmosphere === score
    ? "bg-gray-200 border-black font-bold text-black"
    : "bg-white text-black"
}`}
                              >
                                {score}
                              </button>
                            )
                          )}

                        </div>

                      </div>

                      {/* Pubs & food */}

                      <div className="mb-6">

                        <label className="block font-medium mb-2">
                          Pubs & food
                        </label>

                        <p className="text-sm text-gray-500 mb-2">
                          Pubs, restaurants and
                          food & drink options
                          around the stadium.
                        </p>

                        <div className="flex gap-2 flex-wrap">

                          {[1,2,3,4,5,6,7,8,9,10].map(
                            (score) => (
                              <button
                                key={score}
                                type="button"
                                onClick={() =>
                                  setReviewPubs(
                                    score
                                  )
                                }
                               className={`border rounded-lg px-3 py-2 ${
  reviewPubs === score
    ? "bg-gray-200 border-black font-bold text-black"
    : "bg-white text-black"
}`}
                              >
                                {score}
                              </button>
                            )
                          )}

                        </div>

                      </div>

                      {/* Getting there */}

                      <div className="mb-6">

                        <label className="block font-medium mb-2">
                          Getting there
                        </label>

                        <p className="text-sm text-gray-500 mb-2">
                          Transport, parking and
                          how easy the stadium is
                          to reach.
                        </p>

                        <div className="flex gap-2 flex-wrap">

                          {[1,2,3,4,5,6,7,8,9,10].map(
                            (score) => (
                              <button
                                key={score}
                                type="button"
                                onClick={() =>
                                  setReviewGettingThere(
                                    score
                                  )
                                }
                               className={`border rounded-lg px-3 py-2 ${
  reviewGettingThere === score
    ? "bg-gray-200 border-black font-bold text-black"
    : "bg-white text-black"
}`}
                              >
                                {score}
                              </button>
                            )
                          )}

                        </div>

                      </div>

                      {/* Stadium experience */}

                      <div className="mb-6">

                        <label className="block font-medium mb-2">
                          Stadium experience
                        </label>

                        <p className="text-sm text-gray-500 mb-2">
                          Seating, concourses,
                          toilets, cleanliness,
                          food & drink and
                          general stadium quality.
                        </p>

                        <div className="flex gap-2 flex-wrap">

                          {[1,2,3,4,5,6,7,8,9,10].map(
                            (score) => (
                              <button
                                key={score}
                                type="button"
                                onClick={() =>
                                  setReviewFacilities(
                                    score
                                  )
                                }
                               className={`border rounded-lg px-3 py-2 ${
  reviewFacilities === score
    ? "bg-gray-200 border-black font-bold text-black"
    : "bg-white text-black"
}`}
                              >
                                {score}
                              </button>
                            )
                          )}

                        </div>

                      </div>

                      {/* Recommend */}

                      <div className="mb-6">

                        <label className="block font-medium mb-2">
                          Would you recommend
                          this away day?
                        </label>

                        <div className="flex gap-3">

                          <button
                            type="button"
                            onClick={() =>
                              setReviewRecommend(
                                true
                              )
                            }
                           className={`border rounded-lg px-4 py-2 ${
  reviewRecommend === true
    ? "bg-gray-200 border-black font-bold text-black"
    : "bg-white text-black"
}`}
                          >
                            Yes
                          </button>

                          <button
                            type="button"
                            onClick={() =>
                              setReviewRecommend(
                                false
                              )
                            }
                          className={`border rounded-lg px-4 py-2 ${
  reviewRecommend === false
    ? "bg-gray-200 border-black font-bold text-black"
    : "bg-white text-black"
}`}
                          >
                            No
                          </button>

                        </div>

                      </div>

                      {/* Review actions */}

                      <div className="flex gap-3">

                        <button
  type="button"
  onClick={closeReviewForm}
  className="border border-gray-400 rounded-lg px-5 py-2 font-medium text-black bg-white hover:bg-gray-100"
>
  Skip for now
</button>

  <button
  type="button"
  onClick={submitReview}
disabled={
  reviewSaving ||
  (
    reviewRecommend === null &&
    completedReviewScores.length === 0
  )
}
  className="bg-white text-black border border-black rounded-lg px-5 py-2 font-bold hover:bg-gray-100 disabled:bg-gray-200 disabled:text-gray-400 disabled:border-gray-300"
>
  {reviewSaving
    ? "Saving..."
    : "Submit Review"}
</button>

                      </div>

                    </div>
                  )}

                </div>
              );
            })}

          </div>
        )}

      {/* =====================================================
          ADD STADIUM
          ===================================================== */}

      <section>

        <h2 className="text-2xl font-semibold mb-2">
          Add Stadium
        </h2>

        <p className="text-gray-600 mb-6">
          Add a stadium you've visited to your
          stadium log.
        </p>

        {/* Search */}

        <div className="flex gap-3 mb-6">

          <input
            type="text"
            value={query}
            onChange={(event) =>
              setQuery(event.target.value)
            }
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                searchVenues();
              }
            }}
            placeholder="Search stadium or city..."
            className="border rounded-lg px-4 py-3 flex-1"
          />

          <button
            type="button"
            onClick={searchVenues}
            disabled={
              searching ||
              query.trim().length < 2
            }
            className="border rounded-lg px-5 py-3"
          >
            {searching
              ? "Searching..."
              : "Search"}
          </button>

        </div>

        {/* Error */}

        {error && (
          <div className="border border-red-300 rounded-lg p-4 mb-6">
            {error}
          </div>
        )}

        {/* Search results */}

        {!selectedVenue &&
          venues.length > 0 && (
            <div className="border rounded-xl overflow-hidden mb-8">

              {venues.map((venue) => {

                const venueAlreadyAdded =
                  reviews.some(
                    (review) =>
                      review.venue_id ===
                      venue.venue_id
                  );

                return (
                  <button
                    key={venue.venue_id}
                    type="button"
                    onClick={() =>
                      setSelectedVenue(
                        venue
                      )
                    }
                    className="w-full text-left p-4 border-b last:border-b-0 hover:bg-gray-100"
                  >

                    <div className="flex justify-between items-center gap-4">

                      <div>
                        <div className="font-semibold">
                          {venue.name}
                        </div>

                        {venue.city && (
                          <div className="text-gray-600">
                            {venue.city}
                          </div>
                        )}
                      </div>

                      {venueAlreadyAdded && (
                        <span className="text-sm font-medium">
                          ✓ Added
                        </span>
                      )}

                    </div>

                  </button>
                );
              })}

            </div>
          )}

        {/* Selected stadium */}

        {selectedVenue && (
          <div className="border rounded-xl p-6">

            <div className="flex justify-between items-start gap-4 mb-6">

              <div>
                <h3 className="text-xl font-semibold mb-1">
                  {selectedVenue.name}
                </h3>

                {selectedVenue.city && (
                  <p className="text-gray-600">
                    {selectedVenue.city}
                  </p>
                )}
              </div>

              {alreadyAdded && (
                <span className="font-medium">
                  ✓ Added
                </span>
              )}

            </div>

            {!alreadyAdded && (
              <>
                <label className="block font-medium mb-2">
                  Visit date
                  <span className="font-normal text-gray-500">
                    {" "}
                    (optional)
                  </span>
                </label>

                <input
                  type="date"
                  value={visitDate}
                  onChange={(event) =>
                    setVisitDate(
                      event.target.value
                    )
                  }
                  className="border rounded-lg px-4 py-3 mb-6"
                />
              </>
            )}

            <div className="flex gap-3">

              <button
                type="button"
                onClick={() =>
                  setSelectedVenue(null)
                }
                className="border rounded-lg px-5 py-3"
              >
                Change stadium
              </button>

              {!alreadyAdded && (
                <button
                  type="button"
                  onClick={addStadium}
                  disabled={saving}
                  className="border rounded-lg px-5 py-3 font-medium"
                >
                  {saving
                    ? "Adding..."
                    : "Add to My Stadiums"}
                </button>
              )}

            </div>

            {alreadyAdded && (
              <p className="mt-4 text-gray-600">
                This stadium is already in your
                stadium log.
              </p>
            )}

          </div>
        )}

        {/* No results */}

        {!searching &&
          query.trim().length >= 2 &&
          venues.length === 0 &&
          !selectedVenue && (
            <p className="text-gray-600">
              No stadiums found.
            </p>
          )}

      </section>

    </main>
  );
}