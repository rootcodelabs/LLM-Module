import React from 'react';
import { MdOutlineWest, MdOutlineEast } from 'react-icons/md';
import clsx from 'clsx';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

interface PaginationProps {
  pageCount: number;
  pageIndex: number;
  canPreviousPage: boolean;
  canNextPage: boolean;
  onPageChange: (pageIndex: number) => void;
  id?: string;
}

const Pagination: React.FC<PaginationProps> = ({
  pageCount,
  pageIndex,
  canPreviousPage,
  canNextPage,
  onPageChange,
  id,
}) => {
  const { t } = useTranslation();
  return (
    <div className="data-table__pagination-wrapper">
      {pageCount > 1 && (
        <div className="data-table__pagination">
          <button
            className="previous"
            onClick={() => onPageChange(pageIndex - 1)}
            disabled={!canPreviousPage}
          >
            <MdOutlineWest />
          </button>
          <nav role="navigation" aria-label={t('global.paginationNavigation') ?? ''}>
            <ul className="links">
              {[...Array(pageCount)].map((_, index) => (
                <li
                  key={`${id}-${index}`}
                  className={clsx({ active: pageIndex === index + 1 })}
                >
                  <Link
                    to={''}
                    onClick={() => onPageChange(index + 1)}
                    aria-label={t('global.goToPageNumber', { page: index + 1 }) ?? ''}
                    aria-current={pageIndex === index + 1 ? 'page' : undefined}
                  >
                    {index + 1}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <button
            className="next"
            onClick={() => onPageChange(pageIndex + 1)}
            disabled={!canNextPage}
          >
            <MdOutlineEast />
          </button>
        </div>
      )}
    </div>
  );
};

export default Pagination;
