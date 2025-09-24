import { FC, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, FormSelect } from 'components';
import Pagination from 'components/molecules/Pagination';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { formattedArray } from 'utils/commonUtilts';
import DataModelCard from 'components/molecules/LLMConnectionCard';
import CircularSpinner from 'components/molecules/CircularSpinner/CircularSpinner';
import { ButtonAppearanceTypes } from 'enums/commonEnums';
import NoDataView from 'components/molecules/NoDataView';
import './LLMConnections.scss';
import { platforms, trainingStatuses } from 'config/dataModelsConfig';
import LLMConnectionCard from 'components/molecules/LLMConnectionCard';
import { fetchLLMConnectionsPaginated, LLMConnectionFilters, LLMConnection } from 'services/llmConnections';
import { llmConnectionsQueryKeys } from 'utils/queryKeys';

const LLMConnections: FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [pageIndex, setPageIndex] = useState<number>(1);
  const [filters, setFilters] = useState<LLMConnectionFilters>({
    pageNumber: 1,
    pageSize: 10,
    sortBy: 'createdAt',
    sortOrder: 'desc',
  });

  // Fetch LLM connections using TanStack Query with new paginated endpoint
  const { data: connectionsResponse, isLoading: isModelDataLoading, error } = useQuery({
    queryKey: llmConnectionsQueryKeys.paginatedList(filters),
    queryFn: () => fetchLLMConnectionsPaginated(filters),
  });

  const llmConnections = connectionsResponse;
  const totalPages = connectionsResponse?.[0]?.totalPages || 1;

  // Update filters when pageIndex changes
  useEffect(() => {
    setFilters(prev => ({ ...prev, pageNumber: pageIndex }));
  }, [pageIndex]);

  const handleFilterChange = (
    name: string,
    value: string | number | undefined | { name: string; id: string }
  ) => {
    let filterUpdate: Partial<LLMConnectionFilters> = {};
    
    if (name === 'sorting') {
      // Handle legacy sorting format
      const sortingValue = value as string;
      const [sortBy, sortOrder] = sortingValue.split(' ');
      
      // Convert snake_case to camelCase for sorting fields
      let camelCaseSortBy = sortBy;
      if (sortBy === 'created_at') camelCaseSortBy = 'createdAt';
      else if (sortBy === 'updated_at') camelCaseSortBy = 'updatedAt';
      else if (sortBy === 'llm_platform') camelCaseSortBy = 'llmPlatform';
      else if (sortBy === 'llm_model') camelCaseSortBy = 'llmModel';
      else if (sortBy === 'monthly_budget') camelCaseSortBy = 'monthlyBudget';
      
      filterUpdate = {
        sortBy: camelCaseSortBy,
        sortOrder: sortOrder as 'asc' | 'desc'
      };
    } else {
      filterUpdate = { [name]: value };
    }

    setFilters((prevFilters) => ({
      ...prevFilters,
      ...filterUpdate,
    }));
    
    // Reset to first page when filters change
    if (name !== 'pageNumber') {
      setPageIndex(1);
    }
  };

  // Platform filter options
  const platformOptions = [
    { label: 'All Platforms', value: 'all' },
    { label: 'OpenAI', value: 'OpenAI' },
    { label: 'Anthropic', value: 'Anthropic' },
    { label: 'Azure OpenAI', value: 'Azure OpenAI' },
    { label: 'Google AI', value: 'Google AI' },
  ];

  // Environment filter options
  const environmentOptions = [
    { label: 'All Environments', value: 'all' },
    { label: 'Testing', value: 'Testing' },
    { label: 'Production', value: 'Production' },
    { label: 'Development', value: 'Development' },
  ];

  // Sort options - converting to new camelCase format
  const sortOptions = [
    { label: 'Created Date (Newest)', value: 'createdAt desc' },
    { label: 'Created Date (Oldest)', value: 'createdAt asc' },
    { label: 'Platform A-Z', value: 'llmPlatform asc' },
    { label: 'Platform Z-A', value: 'llmPlatform desc' },
    { label: 'Budget (High to Low)', value: 'monthlyBudget desc' },
    { label: 'Budget (Low to High)', value: 'monthlyBudget asc' },
  ];

  const currentSorting = `${filters.sortBy || 'createdAt'} ${filters.sortOrder || 'desc'}`;

  // Find featured connection (first active one)
  const featuredConnection = llmConnections?.[0];
  const otherConnections = llmConnections || [];

  return (
    <div>
      <div className="container">
        {!isModelDataLoading ? (
          <div>
            <div>
              <div className="title_container">
                <div className="title">{t('dataModels.dataModels')}</div>
                <Button
                  appearance="primary"
                  size="m"
                  onClick={() => navigate('/create-llm-connection')}
                >
                  {'Create LLM Connection'}
                </Button>
              </div>
              <div className="search-panel">
                <div className="models-filter-div">
                  <FormSelect
                    label=""
                    name="llmPlatform"
                    placeholder={'Platform'}
                    options={platformOptions}
                    onSelectionChange={(selection) =>
                      handleFilterChange('llmPlatform', selection?.value ?? '')
                    }
                    defaultValue={filters?.llmPlatform || 'all'}
                  />
                  <FormSelect
                    label=""
                    name="environment"
                    placeholder={'Environment'}
                    options={environmentOptions}
                    onSelectionChange={(selection) =>
                      handleFilterChange('environment', selection?.value)
                    }
                    defaultValue={filters?.environment || 'all'}
                  />

                  <FormSelect
                    label=""
                    name="sorting"
                    placeholder={'Sort By'}
                    options={sortOptions}
                    onSelectionChange={(selection) =>
                      handleFilterChange('sorting', selection?.value)
                    }
                    defaultValue={currentSorting}
                  />

                  <div className="filter-reset-button">
                    <Button
                      onClick={() => {
                        setFilters({
                          pageNumber: 1,
                          pageSize: 10,
                          sortBy: 'createdAt',
                          sortOrder: 'desc',
                        });
                        setPageIndex(1);
                      }}
                      appearance={ButtonAppearanceTypes.SECONDARY}
                    >
                      {t('global.reset') ?? 'Reset'}
                    </Button>
                  </div>
                </div>
              </div>

              {featuredConnection && (
                <div className="m-30-0">
                  <p>Production LLM Connection</p>
                  <div className="grid-container m-30-0">
                    <LLMConnectionCard
                      key={featuredConnection.id}
                      llmConnectionId={featuredConnection.id}
                      llmConnectionName={`${featuredConnection.llmPlatform} - ${featuredConnection.llmModel}`}
                      isActive={featuredConnection.status === 'active'}
                      deploymentEnv={featuredConnection.environment}
                      budgetStatus="healthy"
                      platform={featuredConnection.llmPlatform}
                      model={featuredConnection.llmModel}
                    />
                  </div>
                </div>
              )}

              {otherConnections?.length > 0 ? (
                <div>
                  <p>Other LLM Connections</p>
                  <div className="grid-container m-30-0">
                    {otherConnections?.map((llmConnection: LLMConnection) => {
                      return (
                        <LLMConnectionCard
                          key={llmConnection.id}
                          llmConnectionId={llmConnection.id}
                          llmConnectionName={`${llmConnection.llmPlatform} - ${llmConnection.llmModel}`}
                          isActive={llmConnection.status === 'active'}
                          deploymentEnv={llmConnection.environment}
                          budgetStatus="healthy"
                          platform={llmConnection.llmPlatform}
                          model={llmConnection.llmModel}
                        />
                      );
                    })}
                  </div>
                </div>
              ) : !featuredConnection ? (
                <NoDataView text={t('dataModels.noModels') ?? 'No LLM connections found'} />
              ) : null}

              {(error as any) && (
                <div className="error-message" style={{ color: 'red', padding: '20px' }}>
                  <p>Error loading LLM connections. Please try again.</p>
                </div>
              )}
            </div>
            <Pagination
              pageCount={totalPages}
              pageIndex={pageIndex}
              canPreviousPage={pageIndex > 1}
              canNextPage={pageIndex < totalPages}
              onPageChange={setPageIndex}
            />
          </div>
        ) : (
          <CircularSpinner />
        )}
      </div>
    </div>
  );
};

export default LLMConnections;
