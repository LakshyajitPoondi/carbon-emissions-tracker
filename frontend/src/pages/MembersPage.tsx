import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import { useAuth } from "../context/AuthContext";
import type {
  JoinRequest,
  OrganizationMember,
  OrganizationRole,
} from "../types";
import { hasOrganizationWriteAccess } from "../utils/organizationRoles";

const ROLES: OrganizationRole[] = ["OWNER", "ADMIN", "EMPLOYEE"];

export function MembersPage() {
  const {
    organization,
    selectOrganization,
    revalidateOrganizations,
  } = useAppState();
  const { email: currentEmail } = useAuth();
  const canManage = hasOrganizationWriteAccess(organization?.role);
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [requests, setRequests] = useState<JoinRequest[]>([]);
  const [joinCode, setJoinCode] = useState<string | null>(null);
  const [memberRoles, setMemberRoles] = useState<Record<number, OrganizationRole>>({});
  const [requestRoles, setRequestRoles] = useState<Record<number, OrganizationRole>>({});
  const [loading, setLoading] = useState(false);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    if (!organization) return;
    setLoading(true);
    setError(null);
    try {
      const loadedMembers = await apiClient.listOrganizationMembers(organization.id);
      setMembers(loadedMembers);
      setMemberRoles(
        Object.fromEntries(loadedMembers.map((member) => [member.user_id, member.role])),
      );
      if (hasOrganizationWriteAccess(organization.role)) {
        const [code, pending] = await Promise.all([
          apiClient.getOrganizationJoinCode(organization.id),
          apiClient.listPendingJoinRequests(organization.id),
        ]);
        setJoinCode(code.join_code);
        setRequests(pending);
        setRequestRoles(
          Object.fromEntries(pending.map((request) => [request.id, "EMPLOYEE"])),
        );
      } else {
        setJoinCode(null);
        setRequests([]);
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [organization]);

  useEffect(() => {
    void load();
  }, [load]);

  async function regenerateCode() {
    if (!organization || !window.confirm("Invalidate the current join code and create a new one?")) {
      return;
    }
    setWorkingId("join-code");
    setError(null);
    try {
      const result = await apiClient.regenerateOrganizationJoinCode(organization.id);
      setJoinCode(result.join_code);
    } catch (err) {
      setError(err);
    } finally {
      setWorkingId(null);
    }
  }

  async function decide(request: JoinRequest, approve: boolean) {
    if (!organization) return;
    setWorkingId(`request-${request.id}`);
    setError(null);
    try {
      if (approve) {
        await apiClient.approveJoinRequest(organization.id, request.id, {
          role: requestRoles[request.id] ?? "EMPLOYEE",
        });
      } else {
        await apiClient.rejectJoinRequest(organization.id, request.id);
      }
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setWorkingId(null);
    }
  }

  async function saveRole(member: OrganizationMember) {
    if (!organization) return;
    setWorkingId(`member-${member.user_id}`);
    setError(null);
    try {
      const updated = await apiClient.updateOrganizationMemberRole(organization.id, member.user_id, {
        role: memberRoles[member.user_id],
      });
      revalidateOrganizations();
      if (member.email === currentEmail && updated.role === "EMPLOYEE") {
        setMembers((current) =>
          current.map((item) => item.user_id === updated.user_id ? updated : item),
        );
      } else {
        await load();
      }
    } catch (err) {
      setError(err);
    } finally {
      setWorkingId(null);
    }
  }

  async function remove(member: OrganizationMember) {
    if (
      !organization ||
      !window.confirm(`Remove ${member.email} from ${organization.name}?`)
    ) {
      return;
    }
    setWorkingId(`member-${member.user_id}`);
    setError(null);
    try {
      await apiClient.removeOrganizationMember(organization.id, member.user_id);
      if (member.email === currentEmail) selectOrganization(null);
      revalidateOrganizations();
      if (member.email !== currentEmail) await load();
    } catch (err) {
      setError(err);
    } finally {
      setWorkingId(null);
    }
  }

  if (!organization) {
    return (
      <main className="page">
        <h1>Members</h1>
        <section className="card empty-state">
          Select or create an organization on Setup before viewing its members.
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <h1>Members</h1>
      <p className="page__intro">
        Manage access to <strong>{organization.name}</strong>. Every member&rsquo;s role applies only
        to this organization.
      </p>

      {error !== null && <ErrorBanner error={error} onRetry={load} />}
      {loading && members.length === 0 ? (
        <LoadingState label="Loading members…" />
      ) : (
        <>
          {canManage && (
            <section className="card">
              <h2>Join code</h2>
              <p className="result-panel__meta">
                Share this private code out of band. It only creates a request; access still
                requires approval.
              </p>
              <div className="join-code-row">
                <code>{joinCode ?? "Loading…"}</code>
                <button
                  type="button"
                  disabled={!joinCode}
                  onClick={() => joinCode && void navigator.clipboard.writeText(joinCode)}
                >
                  Copy
                </button>
                <button
                  type="button"
                  disabled={workingId === "join-code"}
                  onClick={() => void regenerateCode()}
                >
                  {workingId === "join-code" ? "Regenerating…" : "Regenerate"}
                </button>
              </div>
            </section>
          )}

          {canManage && (
            <section className="card">
              <h2>Pending requests</h2>
              {requests.length === 0 ? (
                <p className="empty-state">There are no pending join requests.</p>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Requester</th>
                      <th scope="col">Requested</th>
                      <th scope="col">Role to grant</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {requests.map((request) => (
                      <tr key={request.id}>
                        <td>{request.user_email}</td>
                        <td>{new Date(request.requested_at).toLocaleString()}</td>
                        <td>
                          <select
                            aria-label={`Role for ${request.user_email}`}
                            value={requestRoles[request.id] ?? "EMPLOYEE"}
                            onChange={(event) =>
                              setRequestRoles((current) => ({
                                ...current,
                                [request.id]: event.target.value as OrganizationRole,
                              }))
                            }
                          >
                            {ROLES.map((role) => <option key={role}>{role}</option>)}
                          </select>
                        </td>
                        <td>
                          <div className="button-row button-row--compact">
                            <button
                              type="button"
                              disabled={workingId === `request-${request.id}`}
                              onClick={() => void decide(request, true)}
                            >
                              Approve
                            </button>
                            <button
                              type="button"
                              className="button--danger"
                              disabled={workingId === `request-${request.id}`}
                              onClick={() => void decide(request, false)}
                            >
                              Reject
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          <section className="card">
            <h2>Current members</h2>
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Email</th>
                  <th scope="col">Role</th>
                  <th scope="col">Joined</th>
                  {canManage && <th scope="col">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.user_id}>
                    <td>{member.email}{member.email === currentEmail ? " (you)" : ""}</td>
                    <td>
                      {canManage ? (
                        <select
                          aria-label={`Role for ${member.email}`}
                          value={memberRoles[member.user_id] ?? member.role}
                          onChange={(event) =>
                            setMemberRoles((current) => ({
                              ...current,
                              [member.user_id]: event.target.value as OrganizationRole,
                            }))
                          }
                        >
                          {ROLES.map((role) => <option key={role}>{role}</option>)}
                        </select>
                      ) : member.role}
                    </td>
                    <td>{new Date(member.joined_at).toLocaleDateString()}</td>
                    {canManage && (
                      <td>
                        <div className="button-row button-row--compact">
                          <button
                            type="button"
                            disabled={
                              workingId === `member-${member.user_id}` ||
                              memberRoles[member.user_id] === member.role
                            }
                            onClick={() => void saveRole(member)}
                          >
                            Save role
                          </button>
                          <button
                            type="button"
                            className="button--danger"
                            disabled={workingId === `member-${member.user_id}`}
                            onClick={() => void remove(member)}
                          >
                            Remove
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </main>
  );
}
