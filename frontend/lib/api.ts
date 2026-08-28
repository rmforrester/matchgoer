import axios from "axios";
import { getSupabaseBrowserClient } from "./supabase.ts";

const getApiBaseUrl = () => {
  const configuredUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");
  if (configuredUrl) return configuredUrl;

  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  return "http://localhost:8000";
};

const api = axios.create({
  baseURL: getApiBaseUrl(),
  withCredentials: true,
});

api.interceptors.request.use(async (config) => {
  const supabase = getSupabaseBrowserClient();
  if (!supabase || config.headers.Authorization) return config;
  const { data } = await supabase.auth.getSession();
  if (data.session?.access_token) {
    config.headers.Authorization = `Bearer ${data.session.access_token}`;
  }
  return config;
});

export const anonymousApi = axios.create({
  baseURL: getApiBaseUrl(),
  withCredentials: true,
});

export default api;
