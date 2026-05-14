export interface AuthUser {
  id: number;
  username: string;
  email?: string | null;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: AuthUser;
}
