import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";
import { useAuth } from "../contexts/AuthContext.new";

const TenantDashboard: React.FC = () => {
  const [selectedProperty, setSelectedProperty] = useState('prop-001');
  const [period, setPeriod] = useState('2024-03');
  const [properties, setProperties] = useState<Array<{ id: string; name: string; timezone: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [year, month] = period.split('-').map(Number);

  useEffect(() => {
    let cancelled = false;
    SecureAPI.getDashboardProperties()
      .then((items) => {
        if (cancelled) return;
        setProperties(items);
        setSelectedProperty(items[0]?.id || '');
      })
      .catch(() => { if (!cancelled) setError('Failed to load properties'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">Property Management Dashboard</h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">Revenue Overview</h2>
                <p className="text-sm lg:text-base text-gray-600">
                  Monthly performance insights for your properties
                </p>
              </div>
              
              {/* Property Selector */}
              <div className="flex flex-col sm:items-end">
                <label htmlFor="revenue-property" className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  id="revenue-property"
                  value={selectedProperty}
                  onChange={(e) => setSelectedProperty(e.target.value)}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                >
                  {properties.map((property) => (
                    <option key={property.id} value={property.id}>
                      {property.name}
                    </option>
                  ))}
                </select>
                <label htmlFor="revenue-month" className="text-xs font-medium text-gray-700 mt-3 mb-1">Reporting Month</label>
                <input
                  id="revenue-month"
                  type="month"
                  min="0001-01"
                  max="9998-12"
                  value={period}
                  onChange={(event) => setPeriod(event.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {loading && <p>Loading properties...</p>}
            {error && <p role="alert" className="text-red-600">{error}</p>}
            {!loading && !error && properties.length === 0 && <p>No properties available.</p>}
            {!loading && !error && selectedProperty && month && year && (
              <RevenueSummary key={`${selectedProperty}:${period}`} propertyId={selectedProperty} month={month} year={year} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  // Reset selections and in-flight component state when the signed-in user changes.
  return <TenantDashboard key={user?.id} />;
};

export default Dashboard;
