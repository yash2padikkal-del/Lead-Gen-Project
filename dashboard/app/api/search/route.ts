import { NextResponse } from "next/server";
import { randomUUID } from "crypto";

export async function POST(request: Request) {
  try {
    const { keyword, searchLimit } = await request.json();

    if (
      typeof keyword !== "string" ||
      !keyword.trim() ||
      keyword.trim().length > 100
    ) {
      return NextResponse.json(
        { error: "Enter a valid keyword (maximum 100 characters)." },
        { status: 400 }
      );
    }

    const allowedLimits = ["10", "25", "50", "100"];
    const limit = String(searchLimit ?? "25");

    if (!allowedLimits.includes(limit)) {
      return NextResponse.json(
        { error: "Invalid search limit." },
        { status: 400 }
      );
    }

    const token = process.env.GITHUB_TOKEN;
    const owner = process.env.GITHUB_OWNER;
    const repo = process.env.GITHUB_REPO;
    const workflow = process.env.GITHUB_WORKFLOW_ID || "run.yml";
    const branch = process.env.GITHUB_BRANCH || "main";

    if (!token || !owner || !repo) {
      return NextResponse.json(
        { error: "GitHub configuration is missing." },
        { status: 500 }
      );
    }

    const requestId = randomUUID();

    const response = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ref: branch,
          inputs: {
            keyword: keyword.trim(),
            search_limit: limit,
            request_id: requestId,
          },
        }),
      }
    );

    if (!response.ok) {
      const error = await response.text();
      console.error("GitHub dispatch error:", error);

      return NextResponse.json(
        { error: "Could not start the search. Check GitHub configuration." },
        { status: response.status }
      );
    }

    return NextResponse.json({
      success: true,
      message: "Search successfully queued.",
      keyword: keyword.trim(),
      searchLimit: limit,
      requestId,
    });
  } catch (error) {
    console.error("Search trigger error:", error);

    return NextResponse.json(
      { error: "An unexpected error occurred." },
      { status: 500 }
    );
  }
}